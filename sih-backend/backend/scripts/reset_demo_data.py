"""
scripts/reset_demo_data.py — Wipe the prototype's investigation data and reseed
the five scenarios.

    docker exec argus_dev_backend python -m scripts.reset_demo_data
    docker exec argus_dev_backend python -m scripts.reset_demo_data --wipe-only
    docker exec argus_dev_backend python -m scripts.reset_demo_data --seed-only

WHAT IT DELETES
---------------
Investigation data only, in foreign-key order:

    decisions, taint_nodes, traces, anchors, evidence_ledger, alerts,
    audit_log, case_wallets, cases, complaint_wallets, complaints, wallets

WHAT IT DELIBERATELY DOES NOT TOUCH
-----------------------------------
  - The OFAC sanctions registry in Redis (`risk:*` entries with
    source="ofac_sdn"). Those are sovereign designations re-seeded at startup;
    dropping them would silently weaken the sanctions override that runs before
    any ML scoring.
  - ML artifacts, the Neo4j graph, and the Alembic schema itself.

Only Redis keys this system seeded (source="seeded_scenario") and the explorer
transaction cache are cleared, so a reset is safe to run immediately before a
demo without rebuilding anything.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from sqlalchemy import text

from app.db.session import AsyncSessionLocal
from app.services import registry_service
from app.services.scenarios.definitions import ALL_SCENARIOS, all_scenario_addresses
from app.services.scenarios.seeder import seed_all

# Child tables first. `evidence_ledger` and `audit_log` carry no enforced FK to
# cases, but they describe cases — leaving them behind would produce an evidence
# trail for a case that no longer exists.
WIPE_ORDER = [
    "decisions",
    "taint_nodes",
    "traces",
    "anchors",
    "evidence_ledger",
    "audit_log",
    "alerts",
    "case_wallets",
    "cases",
    "complaint_wallets",
    "complaints",
    "wallets",
]


async def wipe_database() -> dict[str, int]:
    """
    One transaction per table, committed as it goes.

    Deliberately not a single transaction: a failure part-way through (a table
    absent on a partial schema, an unexpected foreign key) would roll back every
    delete that had already succeeded, and the script would then report counts
    for rows that are still in the database. That is exactly the bug this
    comment exists to prevent a future edit from reintroducing.
    """
    deleted: dict[str, int] = {}
    for table in WIPE_ORDER:
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(text(f"DELETE FROM {table}"))
                await db.commit()
                deleted[table] = result.rowcount or 0
            except Exception as exc:
                await db.rollback()
                deleted[table] = -1
                print(f"  ! {table}: {exc.__class__.__name__} — {exc}")
    return deleted


async def wipe_redis() -> int:
    """Delete only the risk entries this seeder wrote, plus the tx cache."""
    client = registry_service.get_redis_client()
    removed = 0

    for address, chain in all_scenario_addresses():
        key = registry_service.format_risk_key(chain, address)
        if await client.delete(key):
            removed += 1

    # Any stragglers from a previous scenario set: match on our provenance tag
    # rather than blanket-deleting risk:*, which would take the OFAC seed with it.
    async for key in client.scan_iter(match="risk:*", count=500):
        raw = await client.get(key)
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except (ValueError, TypeError):
            continue
        if payload.get("source") == "seeded_scenario":
            await client.delete(key)
            removed += 1

    async for key in client.scan_iter(match="tx:*", count=500):
        await client.delete(key)

    return removed


async def seed() -> list[dict[str, str]]:
    async with AsyncSessionLocal() as db:
        return await seed_all(db)


async def main(wipe: bool, do_seed: bool) -> int:
    if wipe:
        print("Wiping investigation data...")
        deleted = await wipe_database()
        for table, count in deleted.items():
            if count >= 0:
                print(f"  - {table:<20} {count} row(s)")
        removed = await wipe_redis()
        print(f"  - redis risk entries   {removed} key(s)")

    if do_seed:
        print("\nSeeding scenarios...")
        results = await seed()
        for scenario, result in zip(ALL_SCENARIOS, results):
            print(f"  + {scenario.title}")
            print(f"      key       {scenario.key}")
            print(f"      case      {result['case_id']}")
            print(f"      anchor    {scenario.anchor_address} ({scenario.anchor_chain.value})")
            print(f"      complaints {len(scenario.complaints)}  transactions {len(scenario.txs)}")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wipe-only", action="store_true", help="Delete, do not reseed")
    parser.add_argument("--seed-only", action="store_true", help="Reseed without deleting")
    args = parser.parse_args()

    if args.wipe_only and args.seed_only:
        sys.exit("--wipe-only and --seed-only are mutually exclusive")

    sys.exit(
        asyncio.run(
            main(wipe=not args.seed_only, do_seed=not args.wipe_only)
        )
    )
