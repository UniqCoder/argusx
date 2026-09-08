"""
app/ml/broadened_ood_validation.py — Broadened OOD false-positive validation.

Scores SIX real, known-legitimate high-volume addresses (not synthetic profiles)
through the LIVE /risk feature-extraction path and the Task 1 + Task 3 combined
model (92f relative features + tuned HPs), and reports top-5 SHAP drivers.
A known-illicit OFAC-sanctioned control is scored through the same path and
reported separately (does not gate the false-positive verdict).

Addresses:
  BTC: Bitfinex cold wallet, Binance cold wallet, Binance hot wallet (1.19M txs)
  ETH: Binance-8, Vitalik Buterin, Coinbase ETH (per KNOWN_VASPS registry)

Contrast: the combined model's local-Task-1 improvement was validated only on
Satoshi Genesis (0.0041 LOW) and Ethereum Foundation (0.0043 LOW). If these six
also score consistently low/legitimate, the OOD fix generalizes; otherwise the
Satoshi/ETH-Fdn improvement was overfit to those two anchors -> investigate
before promoting.

Live fetches use the SAME explorers as risk_service:
  BTC: Blockstream Esplora -> Mempool.space   (free public, no API key)
  ETH: eth.blockscout.com                     (free public, no API key)
Requires network access; fetch failures are reported explicitly (not scored 0).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import shap

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.features import (  # noqa: E402
    FEATURE_COLUMNS,
    GSAGE_EMBEDDING_COLUMNS,
    add_embedding_columns,
    compute_tabular_feature_vector,
)
from app.ml.embedding_store import get_live_embeddings
from app.ml.live_graph_features import compute_live_graph_features_with_fallback
from app.ml.model import get_model, map_score_to_tier, predict_risk_score
from app.ml.promotion_experiments import (
    MODEL_PLUS_RELATIVE_COLUMNS,
    add_relative_features,
    load_splits,
    run_combined_relative_tuned,
)
from app.schemas.common import Chain
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer

logger = logging.getLogger(__name__)

REL_COLS = ["total_txs_pctile_era", "value_transacted_total_pctile_era",
            "total_txs_z_era", "value_transacted_total_z_era"]

BRC_ENTITIES = [
    {"label": "bitfinex_cold", "address": "1FfmbHfnpaZjKFvyi1okTjJJusN455paPH", "chain": Chain.BTC},
    {"label": "binance_cold", "address": "3FHNBLobJnbCTFTVakh5TXmEneyf5PT61B", "chain": Chain.BTC},
    {"label": "binance_hot_1.19M", "address": "1NDyJtNTjmwk5xPNhjgAMu4HDHigtobu1s", "chain": Chain.BTC},
    {"label": "binance_8", "address": "0x28C6c06298d514Db089934071355E5743bf21d60", "chain": Chain.ETH},
    {"label": "vitalik_buterin", "address": "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045", "chain": Chain.ETH},
    {"label": "coinbase_eth", "address": "0x503828976D22510aad0201ac7EC88293211D23Da", "chain": Chain.ETH},
]

# Known-illicit controls (OFAC-designated / documented in IMPLEMENTATION_STATUS):
# scored through the SAME path but reported separately — they must NOT gate the
# false-positive verdict, which is computed on BRC_ENTITIES only.
SANCTIONED_ENTITIES = [
    {"label": "garantex_ofac", "address": "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1", "chain": Chain.BTC},
]

ANCHOR_RESULTS = {
    "satoshi_genesis": {"score_92f": 0.0041, "tier": "low"},
    "eth_foundation": {"score_92f": 0.0043, "tier": "low"},
}


def explain_92f(clf, vector: np.ndarray, top_k: int = 5) -> list[dict]:
    """SHAP top-k drivers for the 92-col combined model (does not touch explain.py)."""
    explainer = shap.TreeExplainer(clf)
    sv = explainer.shap_values(vector)
    if isinstance(sv, list):
        vals = sv[1][0]
    else:
        vals = sv[0]
    pairs = []
    for col, val in zip(MODEL_PLUS_RELATIVE_COLUMNS, vals):
        if abs(val) < 1e-4:
            continue
        pairs.append({
            "feature_name": col,
            "contribution": round(float(abs(val)), 4),
            "direction": "increases_risk" if val > 0 else "decreases_risk",
        })
    pairs.sort(key=lambda x: x["contribution"], reverse=True)
    return pairs[:top_k]


def score_92f(clf, base_vec: np.ndarray, embedding: np.ndarray, ref: dict) -> np.ndarray:
    # Post-promotion path: tabular+relative (76) + embedding -> full 92 vector.
    return add_embedding_columns(base_vec, embedding)


async def fetch_txs(entity: dict, limit: int = 25) -> list:
    if entity["chain"] == Chain.BTC:
        return await BitcoinExplorer().get_transactions(entity["address"], limit=limit)
    return await EthereumExplorer().get_transactions(entity["address"], limit=limit)


async def validate_one(clf, ref, prod_model, entity: dict) -> dict:
    chain = entity["chain"]
    addr = entity["address"]

    raw_txs = await fetch_txs(entity)
    fetched = len(raw_txs)

    graph_feats, graph_mode = await compute_live_graph_features_with_fallback(addr, chain.value)
    base_vec = compute_tabular_feature_vector(addr, chain.value, raw_txs, graph_features=graph_feats)
    embedding, emb_mode = await get_live_embeddings(addr, chain.value)

    prod_score = float(predict_risk_score(add_embedding_columns(base_vec, embedding)))
    prod_tier = map_score_to_tier(prod_score).value

    vec92 = score_92f(clf, base_vec, embedding, ref)
    c_score = float(clf.predict_proba(vec92)[0, 1])
    c_tier = map_score_to_tier(c_score).value

    raw92 = [round(float(v), 4) for v in vec92[0]]

    return {
        "label": entity["label"],
        "address": addr,
        "chain": chain.value,
        "tx_events": fetched,
        "fetch_failed": fetched == 0,
        "graph_mode": graph_mode,
        "embedding_mode": emb_mode,
        "production_92f_score": round(prod_score, 4),
        "production_92f_tier": prod_tier,
        "combined_92f_score": round(c_score, 4),
        "combined_92f_tier": c_tier,
        "raw_92_vector": raw92,
        "top_shap_92f": explain_92f(clf, vec92, top_k=5),
    }


async def validate_all() -> dict:
    train_df, val_df, test_df = load_splits()
    res = run_combined_relative_tuned(train_df, val_df, test_df)
    clf = res["clf"]
    ref = res["reference"]
    prod_model = get_model()

    results = []
    controls = []
    sanctioned_labels = {s["label"] for s in SANCTIONED_ENTITIES}
    for entity in BRC_ENTITIES + SANCTIONED_ENTITIES:
        try:
            res = await validate_one(clf, ref, prod_model, entity)
        except Exception as e:  # noqa: BLE001  — report, don't abort the batch
            res = {
                "label": entity["label"],
                "address": entity["address"],
                "chain": entity["chain"].value,
                "fetch_failed": True,
                "error": str(e),
            }
        res["control_group"] = "known_illicit" if entity["label"] in sanctioned_labels else "known_legit"
        bucket = controls if res["control_group"] == "known_illicit" else results
        bucket.append(res)
        print(f"[{entity['label']}] {res.get('combined_92f_score')} "
              f"{res.get('combined_92f_tier')} tx_events={res.get('tx_events')}")

    valid = [r for r in results if not r.get("fetch_failed", False)]
    scores = [r["combined_92f_score"] for r in valid]
    n_low = sum(1 for s in scores if s < 0.30)
    any_high = any(s >= 0.60 for s in scores)
    if len(valid) < len(results) or len(valid) < 6:
        verdict = "investigate"
    elif n_low >= 5 and not any_high:
        verdict = "PASS"
    else:
        verdict = "investigate"

    report = {
        "config": "task1_plus_task3_combined (92f + tuned HPs)",
        "method": "LIVE explorer lookups through the risk_service feature path; no synthetic profiles",
        "tx_limit": 25,
        "tx_window_note": "each on-chain tx yields one RawTx per output leg (exchange txs like "
                          "Bitfinex/Binance consolidation have 2-260+ outputs), matching how "
                          "the production /risk path consumes explorer data",
        "anchors_92f": ANCHOR_RESULTS,
        "verdict_rule": "PASS if >=5/6 known-legit combined scores < 0.30 (LOW) and none >= 0.60; "
                        "fetch failure or any HIGH entity -> investigate before promoting. "
                        "Sanctioned controls (known-illicit) are reported separately and do NOT gate the verdict.",
        "verdict": verdict,
        "n_low_tier": n_low,
        "entities": results,
        "sanctioned_controls": controls,
    }
    out = os.path.join(os.path.dirname(__file__), "artifacts", "broadened_ood_validation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    return asyncio.run(validate_all())


if __name__ == "__main__":
    main()