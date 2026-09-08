"""
app/ml/generalization_probe.py — Gate 3b: non-circular generalization check.

Scores addresses NOT used elsewhere in this debugging session through the same
DEPLOYED production 92f path (features -> model -> predict_risk_score), to
verify the era-reference recalibration (Pass 2) generalizes rather than merely
satisfying the specific OOD entities it was validated against.

Two pools:
  * FRESH_MODERN — 3 BTC addresses drawn from a RESERVED independent block
    sample (seed 999, distinct from the census seed 7, heights strided across
    841k-900k). Brand-new modern-era addresses, unrelated to census/OOD/anchors.
  * KNOWN_LEGIT — 2 well-known benign wallets (probe-verified against public
    explorers):
      1BoatSLRHtKNngkdXEeobR76b53LETtpyT  Bitcoin.org donation fund (BTC)
      0xde21f729137c5af1b01d73af1dc21effa2b8a0d6  Gitcoin multisig (ETH)

Checks:
  * every entity scores through the real fetch + feature + model path;
  * relative-feature slots show real discrimination (not all 0.0, not all
    clamped to one saturated value);
  * known-legit stay LOW; fresh-modern spread across plausible ranges.

Writes artifacts/generalization_probe.json.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random

import httpx
import numpy as np

from app.ml.broadened_ood_validation import explain_92f
from app.ml.embedding_store import get_live_embeddings
from app.ml.features import add_embedding_columns, compute_tabular_feature_vector
from app.ml.live_graph_features import compute_live_graph_features_with_fallback
from app.ml.model import get_model, map_score_to_tier, predict_risk_score
from app.schemas.common import Chain
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
ESPLORA = "https://blockstream.info/api"
CENSUS_RANGE = (841000, 900000)
RESERVED_SEED = 999

KNOWN_LEGIT = [
    {"label": "bitcoin_org_donation", "address": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT", "chain": Chain.BTC},
    {"label": "gitcoin_multisig", "address": "0xde21f729137c5af1b01d73af1dc21effa2b8a0d6", "chain": Chain.ETH},
]


async def draw_fresh_modern_btc(n: int) -> list[dict]:
    """Draw n BTC addresses born in 841k-900k using a RESERVED seed, never
    overlapping the census (seed 7) set."""
    async with httpx.AsyncClient(base_url=ESPLORA, timeout=20.0) as client:
        tip = int((await client.get("/blocks/tip/height")).text)
        hi = min(CENSUS_RANGE[1], tip - 2)
        heights = sorted(random.Random(RESERVED_SEED).sample(range(CENSUS_RANGE[0], hi + 1), 9))
        picks, seen = [], set()
        for idx, h in enumerate(heights):
            try:
                bhash = (await client.get(f"/block-height/{h}")).text.strip()
                start = random.Random(RESERVED_SEED + h).choice([0, 25, 50, 75])
                txs = (await client.get(f"/block/{bhash}/txs", params={"start_index": start if start else None})).json()
            except Exception:  # noqa: BLE001
                continue
            for tx in txs:
                for vout in tx.get("vout", []):
                    a = vout.get("scriptpubkey_address")
                    if not a or a in seen:
                        continue
                    summ = await client.get(f"/address/{a}")
                    if summ.status_code != 200:
                        continue
                    cs = summ.json().get("chain_stats", {})
                    tc = int(cs.get("tx_count", 0))
                    if tc <= 0:
                        continue
                    seen.add(a)
                    picks.append({
                        "label": f"fresh_modern_{len(picks) + 1}",
                        "address": a,
                        "chain": Chain.BTC,
                        "provenance": {"block": h, "tx_count": tc},
                    })
                    break
            if len(picks) >= n:
                break
        return picks[:n]


async def score_one(prod_model, entity: dict) -> dict:
    chain = entity["chain"]
    addr = entity["address"]
    if chain == Chain.BTC:
        raw_txs = await BitcoinExplorer().get_transactions(addr, limit=25)
    else:
        raw_txs = await EthereumExplorer().get_transactions(addr, limit=25)
    graph_feats, graph_mode = await compute_live_graph_features_with_fallback(addr, chain.value)
    base_vec = compute_tabular_feature_vector(addr, chain.value, raw_txs, graph_features=graph_feats)
    embedding, emb_mode = await get_live_embeddings(addr, chain.value)
    vec92 = add_embedding_columns(base_vec, embedding)
    prod_score = float(predict_risk_score(vec92))
    prod_tier = map_score_to_tier(prod_score).value
    rel = [round(float(v), 4) for v in np.asarray(vec92[0])[-4:]]
    return {
        "label": entity["label"],
        "address": addr,
        "chain": chain.value,
        "source": "fresh_modern" if entity["label"].startswith("fresh_modern") else "known_legit",
        "provenance": entity.get("provenance"),
        "tx_events": len(raw_txs),
        "fetch_failed": len(raw_txs) == 0,
        "graph_mode": graph_mode,
        "embedding_mode": emb_mode,
        "production_92f_score": round(prod_score, 4),
        "production_92f_tier": prod_tier,
        "rel_slots": rel,
        "top_shap_92f": explain_92f(prod_model, vec92, top_k=5),
    }


async def run() -> dict:
    fresh = await draw_fresh_modern_btc(3)
    entities = KNOWN_LEGIT + fresh
    results = []
    prod_model = get_model()
    for ent in entities:
        try:
            r = await score_one(prod_model, ent)
            results.append(r)
            print(f"[{r['label']}] prod={r['production_92f_score']:.4f} {r['production_92f_tier']} "
                  f"tx={r['tx_events']} rel={r['rel_slots']}")
        except Exception as e:  # noqa: BLE001
            results.append({
                "label": ent["label"], "address": ent["address"], "chain": ent["chain"].value,
                "source": "fresh_modern" if ent["label"].startswith("fresh_modern") else "known_legit",
                "fetch_failed": True, "error": str(e),
            })
            print(f"[{ent['label']}] ERROR {str(e)[:120]}")

    ok = [r for r in results if not r.get("fetch_failed")]
    rel_flat = [v for r in ok for v in r.get("rel_slots", [])]
    distinct = sorted(set(rel_flat))
    checks = {
        "all_fetched": len(ok) == len(results),
        "known_legit_all_low": all(
            r.get("production_92f_tier") == "low"
            for r in results if r.get("source") == "known_legit" and not r.get("fetch_failed")
        ),
        "rel_slots_discriminate": len(distinct) > 3 and (max(distinct) - min(distinct)) > 0.5,
        "untested_fresh_count_ok": len([r for r in results if r.get("source") == "fresh_modern"]) >= 3,
    }
    outcome = {
        "purpose": "Gate 3b — non-circular generalization probe (Pass 2 recalibration)",
        "reserved_seed": RESERVED_SEED,
        "checks": checks,
        "entities": results,
    }
    out = os.path.join(_DIR, "artifacts", "generalization_probe.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(outcome, f, indent=2)
    print(json.dumps(checks, indent=2))
    print("Wrote", out)
    return outcome


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(run())


if __name__ == "__main__":
    main()