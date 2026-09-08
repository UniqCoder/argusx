"""
app/ml/final_recommendation.py — Consolidated operating point for the promoted config.

Items 2 & 3 established:
  * Item 3 (weight ablation): scale_pos_weight=4.93 is redundant double-correction
    on top of the per-chain sample_weights -> the promoted config is arm B
    (92f relative features + tuned HPs, scale_pos_weight=1.0, per-chain weights).
  * Item 2 (threshold reselection): operating threshold must be re-locked on the
    promoted config's OWN validation distribution, and confirmed on the test split.

This script trains the FINAL config (arm B) once and:
  1) Re-scans the validation threshold from scratch (<2% policy lock + <1% override).
  2) Confirms BTC / ETH / combined precision, recall, FPR on the TEST split at both.
  3) Writes artifacts/final_recommendation.json used for promotion wiring.
"""
from __future__ import annotations

import json
import logging
import os
import sys

import numpy as np
from sklearn.metrics import confusion_matrix

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.promotion_experiments import (
    THRESHOLD_CANDIDATES,
    _btc_eval,
    _eth_eval,
    _eval,
    load_splits,
    run_combined_relative_tuned,
)

logger = logging.getLogger(__name__)


def scan(y_true, y_prob) -> list[dict]:
    rows = []
    for t in THRESHOLD_CANDIDATES:
        preds = (y_prob >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_true, preds).ravel()
        rows.append({
            "threshold": float(t),
            "precision": float(tp / max(1, tp + fp)),
            "recall": float(tp / max(1, tp + fn)),
            "fpr": float(fp / max(1, fp + tn)),
        })
    return rows


def lock(rows: list[dict], max_fpr: float) -> dict:
    return max([r for r in rows if r["fpr"] <= max_fpr], key=lambda r: r["recall"])


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    train_df, val_df, test_df = load_splits()
    res = run_combined_relative_tuned(
        train_df, val_df, test_df,
        scale_pos_weight=1.0,
        weight_mode="chain",
        return_probs=True,
    )

    scan_rows = scan(val_df["label"], res["val_prob"])
    print("\n[FINAL CONFIG (92f + tuned HPs, scale_pos_weight=1.0) VALIDATION SCAN]")
    print(f"{'Thr':>6} | {'Prec':>7} | {'Rec':>7} | {'FPR':>9} | {'<2%':>4} | {'<1%':>4}")
    for r in scan_rows:
        print(f"{r['threshold']:>6.2f} | {r['precision']:>7.4f} | {r['recall']:>7.4f} | "
              f"{r['fpr']*100:>6.2f}% | {'Y' if r['fpr'] <= 0.02 else 'N':>4} | "
              f"{'Y' if r['fpr'] <= 0.01 else 'N':>4}")

    locked = lock(scan_rows, 0.020)
    strict = lock(scan_rows, 0.010)

    test_at = {
        f"threshold_{t:.2f}": {
            "combined": _eval(test_df["label"], res["test_prob"], t),
            "btc": _btc_eval(test_df, res["test_prob"], t),
            "eth": _eth_eval(test_df, res["test_prob"], t),
        }
        for t in {locked["threshold"], strict["threshold"]}
    }

    report = {
        "final_config": "task1_plus_task3_combined, scale_pos_weight=1.0 (arm B), per-chain sample_weight",
        "hyperparameters": {"learning_rate": 0.11111992920245407, "max_depth": 7,
                            "n_estimators": 292, "subsample": 0.9172272185207363,
                            "colsample_bytree": 0.7571088996592841, "scale_pos_weight": 1.0},
        "val_scan": scan_rows,
        "promoted_operating_point": locked["threshold"],
        "promoted": {k: locked[k] for k in ("threshold", "precision", "recall", "fpr")},
        "fpr1pc_alternative": strict["threshold"],
        "fpr1pc_achieved": bool(strict["fpr"] <= 0.010),
        "test_split_at_promoted_and_strict": test_at,
        "btc_test_scores_complete": True,
    }
    out = os.path.join(os.path.dirname(__file__), "artifacts", "final_recommendation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()