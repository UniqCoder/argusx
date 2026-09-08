"""
app/ml/threshold_reselection.py — Re-select the operating threshold from scratch.

The Task 1 + Task 3 combined model produces a new score distribution, so the
legacy 0.92 threshold locked for the old distribution must NOT be assumed. This
script:

  1. Re-runs the threshold scan on the combined model's VALIDATION slice from
     scratch (no reuse of 0.92).
  2. Confirms the 0.85 (locked, <2% FPR policy) vs 0.92 (<1% FPR alternative)
     operating points on the TEST split for BTC / ETH / combined.
  3. Emits a decision: 0.85 is the promoted operating point per docs/ml.md
     policy; 0.92 remains the explicit <1%-FPR override option (recall cost).

Promotion gate (docs/ml.md): lock the highest-recall threshold with combined
validation FPR < 2%. A separate <1% FPR operating point is documented for the
original target owner to review.
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

FPR_2PC = 0.020
FPR_1PC = 0.010


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
            "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
        })
    return rows


def lock(rows: list[dict], max_fpr: float) -> dict:
    ok = [r for r in rows if r["fpr"] <= max_fpr]
    return max(ok, key=lambda r: r["recall"])


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    train_df, val_df, test_df = load_splits()
    res = run_combined_relative_tuned(train_df, val_df, test_df, return_probs=True)
    val_prob = res["val_prob"]
    test_prob = res["test_prob"]

    y_val = val_df["label"]
    scan_rows = scan(y_val, val_prob)

    print("\n[COMBINED MODEL VALIDATION THRESHOLD SCAN — from scratch]")
    print(f"{'Thr':>6} | {'Prec':>7} | {'Rec':>7} | {'FPR':>9} | {'<2%':>4} | {'<1%':>4}")
    for r in scan_rows:
        print(f"{r['threshold']:>6.2f} | {r['precision']:>7.4f} | {r['recall']:>7.4f} | "
              f"{r['fpr']*100:>6.2f}% | {'Y' if r['fpr'] <= FPR_2PC else 'N':>4} | "
              f"{'Y' if r['fpr'] <= FPR_1PC else 'N':>4}")

    locked = lock(scan_rows, FPR_2PC)
    strict = lock(scan_rows, FPR_1PC)
    print(f"\nLocked (FPR<2%): {locked['threshold']}  recall={locked['recall']:.4f}  fpr={locked['fpr']*100:.2f}%")
    print(f"<1% alternative: {strict['threshold']}  recall={strict['recall']:.4f}  fpr={strict['fpr']*100:.2f}%")

    targets = [locked["threshold"], strict["threshold"]]
    test_report = {}
    for t in targets:
        test_report[f"threshold_{t:.2f}"] = {
            "combined": _eval(test_df["label"], test_prob, t),
            "btc": _btc_eval(test_df, test_prob, t),
            "eth": _eth_eval(test_df, test_prob, t),
        }

    report = {
        "config": "task1_plus_task3_combined (92f + tuned HPs)",
        "val_scan": scan_rows,
        "locked_policy_fpr2pc": {
            "threshold": locked["threshold"],
            "val_recall": locked["recall"],
            "val_fpr": locked["fpr"],
            "rule": "highest val recall with combined FPR < 2% (docs/ml.md policy)",
        },
        "strict_fpr1pc_alternative": {
            "threshold": strict["threshold"],
            "val_recall": strict["recall"],
            "val_fpr": strict["fpr"],
        },
        "promoted_operating_point": locked["threshold"],
        "fpr1pc_achieved": bool(strict["fpr"] <= FPR_1PC),
        "fpr1pc_note": f"<1% FPR achievable only at threshold {strict['threshold']:.2f} "
                      f"(val recall {strict['recall']:.3f} vs {locked['recall']:.3f}); "
                      "needs explicit owner sign-off to override the 0.85 policy lock.",
        "test_split_at_both": test_report,
    }
    out = os.path.join(os.path.dirname(__file__), "artifacts", "threshold_reselection.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()