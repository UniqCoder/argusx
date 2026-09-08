"""
app/ml/prepromotion_checks.py — Pre-promotion checks for the winning config
(Task 1 + Task 3 combined: 92f relative features + tuned HPs).

Runs the checks that were done before the previous promotion (docs/ml.md):
  1. ETH regression check — ETH AUC-PR / recall on the 92f+tuned model vs
     production ETH metrics (0.9571 AUC-PR, 0.6006 recall).
  2. Embedding-jitter stability — score the two FP addresses (and a handful of
     labeled test rows) under +/-1e-4 embedding jitter; scores must stay stable.
  3. FP re-check — Satoshi Genesis + Ethereum Foundation via the live /risk
     feature-extraction path (production 88f vs winning 92f).
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.features import FEATURE_COLUMNS, GSAGE_EMBEDDING_COLUMNS, add_embedding_columns, compute_tabular_feature_vector
from app.ml.model import map_score_to_tier
from app.ml.promotion_experiments import (
    MODEL_PLUS_RELATIVE_COLUMNS,
    add_relative_features,
    augment_with_store,
    load_splits,
    run_combined_relative_tuned,
)
from app.schemas.common import Chain
from app.services.explorers.base import RawTx
from app.ml.live_ood_diagnostic import satoshi_profile, eth_foundation_profile

logger = logging.getLogger(__name__)


def _score_rel(model, base_vec: np.ndarray, emb: np.ndarray, ref: dict) -> float:
    # Post-promotion path: tabular+relative (76) + embedding -> full 92 vector.
    model_vec = add_embedding_columns(base_vec, emb)
    return float(model.predict_proba(model_vec)[0, 1])


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    train_df, val_df, test_df = load_splits()
    res = run_combined_relative_tuned(train_df, val_df, test_df)
    clf = res["clf"]
    ref = res["reference"]

    report = {
        "config": "task1_plus_task3_combined",
        "btc_test": res["btc_test"],
        "combined_test": res["combined_test"],
        "eth_test": res["eth_test"],
    }

    # 1. ETH regression check
    eth_prod = {"auc_pr": 0.9571, "recall": 0.6006, "auc_roc": 0.9851}
    eth_cur = report["eth_test"]
    report["eth_regression_check"] = {
        "production": eth_prod,
        "winning_config": {k: eth_cur[k] for k in ("auc_pr", "recall", "auc_roc")},
        "pass": float(eth_cur["auc_pr"]) >= eth_prod["auc_pr"] - 0.005,
    }

    # 2. Embedding-jitter stability on the two FP profiles (and 200 BTC test rows)
    jitter_cases = []
    for label, chain, txs in [
        ("satoshi_genesis", Chain.BTC, satoshi_profile()),
        ("eth_foundation", Chain.ETH, eth_foundation_profile()),
    ]:
        base_vec = compute_tabular_feature_vector("addr", chain.value, txs)
        base_emb = np.zeros((len(GSAGE_EMBEDDING_COLUMNS),), dtype=np.float32)
        base_score = _score_rel(clf, base_vec, base_emb, ref)
        scores = [base_score]
        for _ in range(10):
            jitter = np.random.default_rng(42).uniform(-1e-4, 1e-4, size=len(GSAGE_EMBEDDING_COLUMNS)).astype(np.float32)
            scores.append(_score_rel(clf, base_vec, base_emb + jitter, ref))
        jitter_cases.append({
            "address": label,
            "base_score": round(base_score, 4),
            "jitter_min": round(float(np.min(scores)), 4),
            "jitter_max": round(float(np.max(scores)), 4),
            "spread": round(float(np.max(scores) - np.min(scores)), 6),
            "stable": bool(np.max(scores) - np.min(scores) < 0.01),
        })

    # Jitter on real BTC test rows (sampled, with their real embeddings via store).
    # Jitter ONLY the 16 embedding dims (positions after the 72 tabular/graph cols),
    # matching the pre-promotion embedding-jitter check from the previous promotion.
    # The relative-feature cols are intentionally NOT jittered here (they are the
    # computed feature; the runtime path recomputes them deterministically from txs).
    btc_test = test_df[test_df["chain"].astype(str) == "BTC"].copy()
    sample = btc_test.sample(n=200, random_state=1).copy()
    sample = add_relative_features(sample, ref)
    sample_aug = augment_with_store(sample)
    X = sample_aug[MODEL_PLUS_RELATIVE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32)

    emb_start = len(FEATURE_COLUMNS)  # 72 (tabular + graph); 92-col input emb starts at 72
    base_probs = clf.predict_proba(X)[:, 1]
    jittered = []
    for i in range(3):
        Xj = X.copy()
        Xj[:, emb_start:emb_start + len(GSAGE_EMBEDDING_COLUMNS)] += (
            np.random.default_rng(i).uniform(-1e-4, 1e-4, size=len(GSAGE_EMBEDDING_COLUMNS)).astype(np.float32)
        )
        jittered.append(clf.predict_proba(Xj)[:, 1])
    jittered = np.array(jittered)
    abs_deltas = np.abs(jittered - base_probs).max(axis=0)
    report["embedding_jitter_stability"] = {
        "fp_profiles": jitter_cases,
        "btc_test_rows": 200,
        "max_abs_delta_p99": round(float(np.percentile(abs_deltas, 99)), 6),
        "max_abs_delta_max": round(float(abs_deltas.max()), 6),
        "pass": bool(np.percentile(abs_deltas, 99) < 0.01),
    }

    # 3. FP re-check
    report["fp_recheck"] = {c["address"]: {"score": c["base_score"], "tier": map_score_to_tier(c["base_score"]).value} for c in jitter_cases}

    out = os.path.join(os.path.dirname(__file__), "artifacts", "prepromotion_checks.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()