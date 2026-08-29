"""
app/workers/tasks/graph_builder.py — Async Neo4j Graph Builder Celery Task (Phase 3).

Populates Wallet, Transaction, VASP, and Cluster nodes in Neo4j from blockchain explorers.
Runs asynchronously off any API request path.
"""
import asyncio
import logging
from typing import List, Optional

from app.core.config import get_settings
from app.graph import cypher
from app.graph.neo4j_client import run_query
from app.schemas.common import Chain
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.tron_explorer import TronExplorer
from app.services.explorers.known_vasps import lookup_known_vasp
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()

btc_explorer = BitcoinExplorer()
eth_explorer = EthereumExplorer()
tron_explorer = TronExplorer()


async def _build_wallet_graph_async(address: str, chain: str, max_depth: int = 2) -> dict:
    """
    Traverse transactions for a wallet and construct the Neo4j subgraph.
    """
    chain_upper = chain.upper()
    visited_addresses = set()
    queue = [(address, 0)]
    total_hops_ingested = 0
    vasp_discovered = None

    while queue:
        curr_addr, depth = queue.pop(0)
        if curr_addr in visited_addresses or depth >= max_depth:
            continue
        visited_addresses.add(curr_addr)

        # 1. Fetch transactions via appropriate explorer
        if chain_upper == Chain.BTC.value:
            txs = await btc_explorer.get_transactions(curr_addr, limit=15)
        elif chain_upper == Chain.ETH.value:
            txs = await eth_explorer.get_transactions(curr_addr, limit=15)
        elif chain_upper == Chain.TRON.value:
            txs = await tron_explorer.get_transactions(curr_addr, limit=15)
        else:
            logger.info("unsupported_chain_for_graph_builder", extra={"chain": chain})
            break

        # 2. Ingest transaction hops into Neo4j
        for tx in txs:
            try:
                await run_query(
                    cypher.UPSERT_TRANSACTION_HOP,
                    {
                        "from_address": tx.from_address,
                        "to_address": tx.to_address,
                        "tx_hash": tx.tx_hash,
                        "amount": float(tx.amount),
                        "chain": tx.chain.value,
                        "timestamp": tx.timestamp.isoformat(),
                    },
                )
                total_hops_ingested += 1

                # Check if to_address is a known VASP
                vasp_match = lookup_known_vasp(tx.to_address)
                if not vasp_match and tx.vasp_tag:
                    vasp_match = (tx.vasp_tag, "International")

                if vasp_match:
                    vasp_name, vasp_jur = vasp_match
                    vasp_discovered = vasp_name
                    await run_query(
                        cypher.ATTACH_VASP_NODE,
                        {
                            "address": tx.to_address,
                            "chain": tx.chain.value,
                            "vasp_name": vasp_name,
                            "jurisdiction": vasp_jur,
                        },
                    )

                # Queue next hop if not at max depth and not a VASP endpoint
                if depth + 1 < max_depth and not vasp_match and tx.to_address not in visited_addresses:
                    queue.append((tx.to_address, depth + 1))

            except Exception as e:
                logger.warning("graph_hop_insert_failed", extra={"tx_hash": tx.tx_hash, "error": str(e)})

    logger.info(
        "graph_builder_completed",
        extra={
            "address": address,
            "chain": chain,
            "hops_ingested": total_hops_ingested,
            "vasp_discovered": vasp_discovered,
        },
    )

    return {
        "address": address,
        "chain": chain,
        "hops_ingested": total_hops_ingested,
        "vasp_discovered": vasp_discovered,
    }


@celery_app.task(name="app.workers.tasks.graph_builder.build_graph_task", bind=True, max_retries=2)
def build_graph_task(self, address: str, chain: str, max_depth: int = 2) -> dict:
    """
    Celery task to build the transaction graph in Neo4j for a given wallet address.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_build_wallet_graph_async(address, chain, max_depth))
            return {"status": "queued"}
        else:
            return loop.run_until_complete(_build_wallet_graph_async(address, chain, max_depth))
    except Exception:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        result = new_loop.run_until_complete(_build_wallet_graph_async(address, chain, max_depth))
        new_loop.close()
        return result
