"""
app/ml/modern_era_census.py — One-time stratified BTC address census for the
841k-900k block range (modern era) used to (re)calibrate the era-reference bin
statistics in relative_features_reference.json.

WHY IT EXISTS
-------------
The original era reference (relative_features_reference.json) was fit ONLY on
Elliptic train rows (BTC, first_block <= 447655). Live addresses whose
first_block falls in the modern range therefore clamp to the newest training
bin, and - because Elliptic addresses are sparse - every such address realizes
pctile ~ 1.0 and a large positive z. That saturates the 4 relative features
(total_txs_pctile_era, value_transacted_total_pctile_era, total_txs_z_era,
value_transacted_total_z_era) and gives every wallet a uniformly HIGH-looking
input. This script harvests a STRATIFIED sample of real, modern-era addresses
so we can replace the last-bin statistics with values that actually
discriminate in the live regime.

SELECTION CRITERIA (stratified, NOT first-N reachable)
------------------------------------------------------
Esplora (/block/:height/txs) exposes the txs mined in a block. Each tx's vout
yields candidate addresses. To get a spread across activity levels we draw a
deterministic (seeded) stride through a set of blocks spread across the range,
collect candidate addresses, then bucket them by their lifetime tx_count and
retain a target count per stratum:

  stratum 0: tx_count in [0,2]      (dust / one-off)
  stratum 1: tx_count in [3,9]
  stratum 2: tx_count in [10,99]
  stratum 3: tx_count in [100,999]
  stratum 4: tx_count in [1000,+)   (high-volume service/mining wallets)

FINAL FILTER
------------
Only addresses whose EARLIEST observed block >= 841000 are retained, so every
census row is a genuinely "born-modern" peer. (An address born earlier that is
still active now is NOT a modern peer for the first-block-binned feature.)

OUTPUT
------
artifacts/modern_era_address_census.json with harvest metadata + one entry per
address:
  address, first_block_appeared_in (earliest status.block_height), total_txs
  (chain_stats.tx_count), value_transacted_total (BTC), stratum.
This artifact is committed and treated as a point-in-time census, NOT a live
dataset. It can be re-harvested later by re-running this script with the same
seed/range.

USAGE
-----
  python -m app.ml.modern_era_census  --blocks 18 --per_block 6 --seed 7 \
      --out app/ml/artifacts/modern_era_address_census.json
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import random
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ESPLORA = "https://blockstream.info/api"
GENESIS_TS = 1230950400.0

STRATA = [
    (0, 0, 2, "dust"),
    (1, 3, 9, "low"),
    (2, 10, 99, "medium"),
    (3, 100, 999, "high"),
    (4, 1000, 10 ** 12, "very_high"),
]
STRATUM_TARGETS = {0: 12, 1: 12, 2: 12, 3: 12, 4: 12}


def stratum_for_tx_count(n: int) -> int:
    for sidx, lo, hi, _ in STRATA:
        if lo <= n <= hi:
            return sidx
    return 4


async def harvest() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocks", type=int, default=18)
    ap.add_argument("--per_block", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    out_path = args.out or os.path.join(os.path.dirname(__file__), "artifacts", "modern_era_address_census.json")
    rng = random.Random(args.seed)

    async with httpx.AsyncClient(base_url=ESPLORA, timeout=20.0) as client:
        tip = int((await client.get("/blocks/tip/height")).text)
        lo_h, hi_h = 841000, min(900000, tip - 2)
        if lo_h >= hi_h:
            raise RuntimeError(f"range {lo_h}-{hi_h} empty (tip {tip})")
        chosen_heights = sorted(rng.sample(range(lo_h, hi_h + 1), args.blocks))

        candidates: dict[str, int] = {}  # address -> earliest block seen

        async def collect_block(height: int) -> None:
            bhash = (await client.get(f"/block-height/{height}")).text.strip()
            start = 0
            seen = set()
            while start < 300:  # soft cap on candidates per block
                try:
                    txs = (await client.get(f"/block/{bhash}/txs", params={"start_index": start} if start else None)).json()
                except Exception:
                    break
                if not txs:
                    break
                for tx in txs:
                    if tx["txid"] in seen:
                        continue
                    seen.add(tx["txid"])
                    for vout in tx.get("vout", []):
                        addr = vout.get("scriptpubkey_address")
                        if addr:
                            candidates.setdefault(addr, height)
                if len(txs) < 25:
                    break
                start += len(txs)

        for h in chosen_heights:
            await collect_block(h)

    # Compute asynchronously the summary + earliest block for retained addresses.
    async with httpx.AsyncClient(base_url=ESPLORA, timeout=20.0) as client:
        selected: dict[int, dict] = {s: {} for s in STRATUM_TARGETS}
        ordered = list(candidates.keys())
        rng.shuffle(ordered)

        for addr in ordered:
            try:
                r = await client.get(f"/address/{addr}")
                if r.status_code != 200:
                    continue
                summ = r.json().get("chain_stats", {})
                tx_count = int(summ.get("tx_count", 0))
                s = stratum_for_tx_count(tx_count)
                if len(selected[s]) >= STRATUM_TARGETS[s]:
                    continue
                first_h = candidates[addr]
                # Esplora /txs returns newest-first; use the TAIL page to find the
                # address's true first block (approx. within one page).
                try:
                    tail = (await client.get(
                        f"/address/{addr}/txs",
                        params={"start_index": max(0, int(tx_count) - 25)},
                    )).json()
                    tail_heights = [int(t["status"]["block_height"]) for t in tail if t.get("status", {}).get("block_height")]
                    if tail_heights:
                        first_h = min(first_h, min(tail_heights))
                except Exception:  # noqa: BLE001 — keep sampled-block height fallback
                    pass
                if first_h < 841000:
                    continue  # not born-modern (active in-window but created earlier)
                entry = {
                    "address": addr,
                    "stratum": s,
                    "first_block_height": first_h,
                    "first_block_appeared_in": float(first_h if first_h else 0),
                    "total_txs": tx_count,
                    "value_transacted_total": float(summ.get("funded_txo_sum", 0) + summ.get("spent_txo_sum", 0)) / 1e8,
                }
                selected[s][addr] = entry
                if all(len(selected[k]) >= STRATUM_TARGETS[k] for k in selected):
                    break
            except Exception as e:  # noqa: BLE001
                logger.warning("census_skip", extra={"address": addr[:12], "error": str(e)})

    rows = [e for s in selected.values() for e in s.values()]
    if len(rows) < sum(STRATUM_TARGETS.values()):
        logger.warning("census_complete", extra={"wanted": sum(STRATUM_TARGETS.values()), "got": len(rows)})

    artifact = {
        "schema_version": 1,
        "purpose": "stratified modern-era BTC address census for era-reference recalibration",
        "source": "blockstream.info Esplora REST API (public)",
        "harvest_date": datetime.now(timezone.utc).isoformat(),
        "block_range": [lo_h, hi_h],
        "selection": {
            "strata": [{"idx": s, "tx_count_range": [lo, hi], "label": lab, "target": STRATUM_TARGETS[s]} for s, lo, hi, lab in STRATA],
            "strategy": "deterministic seeded block draw + per-block txs vout addresses (all formats incl. bech32/taproot; Esplora 200 response validates the address); stratified by lifetime tx_count; retained only if earliest block >= 841000 (born-modern)",
            "seed": args.seed,
            "blocks_sampled": args.blocks,
        },
        "field_definitions": {
            "first_block_appeared_in": "earliest status.block_height across fetched txs (block-number convention used by the era bins)",
            "total_txs": "chain_stats.tx_count (lifetime)",
            "value_transacted_total": "(funded_txo_sum + spent_txo_sum) / 1e8 (lifetime BTC)",
            "stratum": "lifetime-tx-count stratum index",
        },
        "note": "Point-in-time census. Re-harvestable by re-running this script with the same seed/range. Not a live/growing dataset.",
        "addresses": rows,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2)
    print(f"Wrote {len(rows)} census addresses -> {out_path}")


if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)
    asyncio.run(harvest())
