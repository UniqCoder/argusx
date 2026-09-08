"""
app/workers/tasks/illicit_enrichment.py — Live-graph illicit-flag enrichment task.

Idempotently marks Wallet nodes in Neo4j with `illicit: true` for known-illicit
addresses (curated sanctions list in app/graph/known_illicit.py plus wallets
linked to enforcement-staged cases). This is what makes the live graph topology
features non-degenerate: without illicit flags, ratio/shortest-path features in
app/ml/live_graph_features.py always evaluate against an empty illicit set.
"""
import asyncio
import structlog
from typing import List

from app.db.session import AsyncSessionLocal
from app.graph.known_illicit import (
    ILLICIT_CASE_STATUSES,
    KNOWN_ILLICIT_WALLETS,
    KnownIllicitWallet,
)
from app.graph.neo4j_client import run_query
from app.models.case import Case, CaseWallet
from app.models.wallet import Wallet
from app.workers.celery_app import celery_app
from sqlalchemy import select

logger = structlog.get_logger(__name__)

# (chain, address) tuples to flag. Persisted sources only — no ad-hoc addresses.
BUILTIN_ENTRIES: list[tuple[str, str, str]] = [
    (w.chain.value, w.address, w.label) for w in KNOWN_ILLICIT_WALLETS
]


async def _query_case_blocked_addresses() -> list[tuple[str, str]]:
    """Return (chain, address) for wallets attached to enforcement-staged cases."""
    rows = []
    async with AsyncSessionLocal() as db:
        stmt = (
            select(Wallet.address, Wallet.chain)
            .join(CaseWallet, CaseWallet.wallet_id == Wallet.id)
            .join(Case, Case.id == CaseWallet.case_id)
            .where(Case.status.in_(ILLICIT_CASE_STATUSES))
        )
        result = await db.execute(stmt)
        rows = [(str(address), str(chain)) for address, chain in result.all()]
    return rows


async def _flag_one(chain: str, address: str, label: str) -> int:
    """Set illicit=true on all Wallet nodes for (chain, address). Returns count flagged."""
    query = """
    MATCH (w:Wallet {address: $address})
    WHERE w.chain = $chain
    SET w.illicit = true
    RETURN count(w) AS flagged
    """
    rows = await run_query(query, {"address": address, "chain": chain})
    if not rows:
        return 0
    return int(rows[0].get("flagged", 0))


async def _enrich_async() -> dict:
    entries: list[tuple[str, str, str]] = list(BUILTIN_ENTRIES)
    case_blocked = await _query_case_blocked_addresses()
    entry_keys = {(c, a) for c, a, _ in entries}
    for chain, address in case_blocked:
        if (chain, address) not in entry_keys:
            entries.append((chain, address, f"case_status:{ILLICIT_CASE_STATUSES}"))
            entry_keys.add((chain, address))

    flagged = 0
    by_entry: list[dict] = []
    for chain, address, label in entries:
        n = await _flag_one(chain, address, label)
        flagged += n
        by_entry.append({"chain": chain, "address": address, "label": label, "flagged": n})
        logger.info(
            "illicit_enrichment_applied",
            chain=chain,
            address=address,
            label=label,
            flagged=n,
        )

    logger.info(
        "illicit_enrichment_completed",
        total_entries=len(entries),
        flagged=flagged,
    )
    return {"total_entries": len(entries), "flagged": flagged, "entries": by_entry}


@celery_app.task(name="app.workers.tasks.illicit_enrichment.enrich_illicit_flags_task")
def enrich_illicit_flags_task() -> dict:
    """Celery task: idempotently flag known-illicit wallets in the live graph."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_enrich_async())
            return {"status": "queued"}
        return loop.run_until_complete(_enrich_async())
    except Exception:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(_enrich_async())
        finally:
            new_loop.close()