"""
app/services/tracing_service.py — Blockchain wallet tracing to nearest VASP.

Resolves multi-hop transaction paths from victim-reported wallets to known exchange deposit hubs.
Strictly layered: Routers -> TracingService -> Neo4j / Explorers / PostgreSQL.
"""
import uuid
from datetime import datetime, timezone
import structlog
from typing import List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.graph import cypher
from app.graph.neo4j_client import run_query
from app.models.wallet import Wallet
from app.schemas.common import Chain, RiskTier
from app.schemas.wallet import Hop, TraceResponse, WalletRead
from app.services.explorers.base import ExplorerUnavailableError
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.tron_explorer import TronExplorer
from app.services.explorers.known_vasps import lookup_known_vasp

logger = structlog.get_logger(__name__)

MAX_TRACE_TRANSFERS = 50

btc_explorer = BitcoinExplorer()
eth_explorer = EthereumExplorer()
tron_explorer = TronExplorer()


async def get_or_create_wallet(
    db: AsyncSession,
    address: str,
    chain: Chain,
) -> Wallet:
    """Retrieve or insert wallet into PostgreSQL."""
    stmt = select(Wallet).where(
        Wallet.address == address,
        Wallet.chain == chain.value,
    )
    res = await db.execute(stmt)
    wallet = res.scalar_one_or_none()

    if wallet is None:
        wallet = Wallet(
            id=uuid.uuid4(),
            address=address,
            chain=chain.value,
            risk_tier=RiskTier.unknown.value,
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
        )
        db.add(wallet)
        await db.commit()
        await db.refresh(wallet)

    return wallet


async def trace_wallet_to_vasp(
    db: AsyncSession,
    address: str,
    chain: Chain,
) -> TraceResponse:
    """
    Trace on-chain transaction path from address to nearest known VASP deposit endpoint.
    1. Looks up or creates wallet in DB.
    2. Queries Neo4j for existing hops.
    3. If none in Neo4j, queries live explorer and populates hops.
    4. Finds shortest path to nearest VASP.
    """
    wallet = await get_or_create_wallet(db, address, chain)
    hops: List[Hop] = []
    nearest_vasp: Optional[str] = None

    if chain not in (Chain.BTC, Chain.ETH, Chain.TRON):
        logger.warning("unsupported_chain_for_tracing", chain=chain.value, address=address)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "UNSUPPORTED_CHAIN",
                    "message": f"Blockchain network '{chain.value}' is not supported for tracing. Supported networks: BTC, ETH, TRON.",
                    "details": {"chain": chain.value},
                }
            },
        )

    # Live explorer data is authoritative for the queried wallet so cached graph
    # edges cannot mask current amounts or return stale fixed-size results. An
    # explorer outage is surfaced as an explicit 503, never a silent empty path.
    try:
        if chain == Chain.BTC:
            raw_txs = await btc_explorer.get_transactions(address, limit=MAX_TRACE_TRANSFERS)
        elif chain == Chain.ETH:
            raw_txs = await eth_explorer.get_transactions(address, limit=MAX_TRACE_TRANSFERS)
        elif chain == Chain.TRON:
            raw_txs = await tron_explorer.get_transactions(address, limit=MAX_TRACE_TRANSFERS)
        else:
            raw_txs = []
    except ExplorerUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": {
                    "code": "explorer_unavailable",
                    "message": f"Blockchain explorer unavailable for {chain.value}: {exc}",
                    "details": {"chain": chain.value, "address": address},
                }
            },
        ) from exc

    if raw_txs:
        for tx in raw_txs:
            hops.append(
                Hop(
                    from_address=tx.from_address,
                    to_address=tx.to_address,
                    tx_hash=tx.tx_hash,
                    amount=tx.amount,
                    chain=tx.chain,
                    timestamp=tx.timestamp,
                )
            )
            if not nearest_vasp and tx.vasp_tag:
                nearest_vasp = tx.vasp_tag
            if not nearest_vasp:
                v_match = lookup_known_vasp(tx.to_address)
                if v_match:
                    nearest_vasp = v_match[0]

    else:
        # Fall back to the persisted graph only when the explorer has no data.
        try:
            records = await run_query(
                cypher.GET_WALLET_HOPS,
                {"address": address, "chain": chain.value, "limit": MAX_TRACE_TRANSFERS},
            )
            # Audit OBSERVABILITY (Group 1): how many hops the Neoo4j fallback
            # actually returned (0 = empty graph, distinct from skipped).
            logger.info(
                "neo4j_hops_query",
                address=address,
                chain=chain.value,
                row_count=len(records),
            )
            for r in records:
                dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) if r.get("timestamp") else datetime.now(timezone.utc)
                hops.append(
                    Hop(
                        from_address=r["from_address"],
                        to_address=r["to_address"],
                        tx_hash=r["tx_hash"],
                        amount=float(r["amount"]),
                        chain=chain,
                        timestamp=dt,
                    )
                )
                if not nearest_vasp and r.get("vasp_name"):
                    nearest_vasp = r["vasp_name"]
        except Exception as e:
            logger.warning("neo4j_hops_query_failed", address=address, chain=chain.value, error=str(e))

    if raw_txs:
        # Trigger async background Neo4j graph builder task for deep multi-hop traversal
        try:
            from app.workers.tasks.graph_builder import build_graph_task
            build_graph_task.apply_async(
                kwargs={"address": address, "chain": chain.value, "max_depth": 2},
                retry=False,
            )
            # Audit OBSERVABILITY (Group 1): was the graph-build actually queued
            # (and consumable), or silently dropped for lack of a worker?
            logger.info(
                "graph_builder_task_dispatched",
                address=address,
                chain=chain.value,
                queued=True,
            )
        except Exception as e:
            logger.warning(
                "graph_builder_dispatch_failed",
                address=address,
                chain=chain.value,
                queued=False,
                error=str(e),
            )

    # 3. Update VASP attribution in PostgreSQL if found
    if nearest_vasp and wallet.vasp_identified != nearest_vasp:
        wallet.vasp_identified = nearest_vasp
        await db.commit()
        await db.refresh(wallet)

    return TraceResponse(
        wallet=WalletRead.model_validate(wallet),
        path=hops,
        nearest_vasp=nearest_vasp,
        hops_count=len(hops),
        traced_at=datetime.now(timezone.utc),
    )
