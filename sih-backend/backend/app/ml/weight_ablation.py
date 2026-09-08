"""
app/ml/weight_ablation.py — Isolate scale_pos_weight vs per-chain sample_weight.

The Optuna tuning (Task 3) selected scale_pos_weight=4.93 ON TOP of the
production per-chain sample_weights (which already class-balance within chain
and equalize BTC/ETH total mass). Because XGBoost multiplies scale_pos_weight
into the sample weights of positive rows, the two mechanisms STACK. This script
abides them apart to find where the combined config's recall gain actually
comes from.

Arms (identical 92f features + identical tuned HPs; threshold re-locked on each
arm's OWN validation scan):
  A  chain sample_weight  + spw 4.93  -> current combined (control)
  B  chain sample_weight  + spw 1.0   -> isolate scale_pos_weight
  C  uniform 1.0          + spw 4.93  -> isolate per-chain sample_weight
  D  uniform 1.0          + spw 1.0   -> both-neutral floor (tuned HPs alone)

Verdict rule: if B is within 0.005 BTC test AUC-PR and 1pp recall of A, the
tuned scale_pos_weight is redundant double-correction -> promote with spw=1.0.
If C is within the same tolerance of A, per-chain sample_weight is not the
lever. Neither match -> the co-tuning of both mechanisms is real.
"""
from __future__ import annotations

import json
import logging
import os
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.promotion_experiments import load_splits, run_combined_relative_tuned

logger = logging.getLogger(__name__)

SPW_TUNED = 4.931116282851712
TOL_AUC_PR = 0.005
TOL_RECALL = 0.010


def arm_results(train_df, val_df, test_df, weight_mode: str, scale_pos_weight: float, label: str) -> dict:
    res = run_combined_relative_tuned(
        train_df, val_df, test_df,
        scale_pos_weight=scale_pos_weight,
        weight_mode=weight_mode,
        return_probs=True,
    )
    out = {
        "arm": label,
        "weight_mode": weight_mode,
        "scale_pos_weight": scale_pos_weight,
        "locked_threshold": res["threshold"],
        "val_summary": {k: res["val_summary"][k] for k in ("threshold", "precision", "recall", "fpr")},
        "btc_test": res["btc_test"],
        "eth_test": res["eth_test"],
        "combined_test": res["combined_test"],
    }
    b = res["btc_test"]
    print(f"[{label}] thr={out['locked_threshold']:.2f}  BTC AUC-PR={b['auc_pr']:.4f} "
          f"recall={b['recall']:.4f} prec={b['precision']:.4f} fpr={b['fpr']*100:.2f}%")
    return out


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    train_df, val_df, test_df = load_splits()

    arms = [
        arm_results(train_df, val_df, test_df, "chain", SPW_TUNED, "A_chain_spw4.93"),
        arm_results(train_df, val_df, test_df, "chain", 1.0, "B_chain_spw1.0"),
        arm_results(train_df, val_df, test_df, "uniform", SPW_TUNED, "C_uniform_spw4.93"),
        arm_results(train_df, val_df, test_df, "uniform", 1.0, "D_uniform_spw1.0"),
    ]

    a = next(a for a in arms if a["arm"] == "A_chain_spw4.93")
    b = next(a for a in arms if a["arm"] == "B_chain_spw1.0")
    c = next(a for a in arms if a["arm"] == "C_uniform_spw4.93")

    a_pr, a_rec = a["btc_test"]["auc_pr"], a["btc_test"]["recall"]
    b_pr, b_rec = b["btc_test"]["auc_pr"], b["btc_test"]["recall"]
    c_pr, c_rec = c["btc_test"]["auc_pr"], c["btc_test"]["recall"]

    spw_redundant = abs(b_pr - a_pr) <= TOL_AUC_PR and abs(b_rec - a_rec) <= TOL_RECALL
    sw_not_lever = abs(c_pr - a_pr) <= TOL_AUC_PR and abs(c_rec - a_rec) <= TOL_RECALL

    if spw_redundant:
        mechanism = "scale_pos_weight is redundant double-correction on top of per-chain sample_weight (B ~= A); promote with scale_pos_weight=1.0 (arm B / neutral)"
    elif not spw_redundant and sw_not_lever:
        mechanism = "scale_pos_weight is the lever; removing per-chain sample_weight does not change BTC metrics (C ~= A)"
    elif spw_redundant and sw_not_lever:
        mechanism = "both mechanisms individually redundant vs neutral floor (check D)"
    else:
        mechanism = "co-tuning of both mechanisms is real: neither alone reproduces arm A"

    report = {
        "config": "task1_plus_task3_combined (92f + tuned HPs)",
        "tolerance": {"auc_pr": TOL_AUC_PR, "recall_pp": TOL_RECALL},
        "recommend": "promote_with_spw_neutral" if spw_redundant else "keep_tuned_spw",
        "mechanism_finding": mechanism,
        "arms": arms,
    }
    out = os.path.join(os.path.dirname(__file__), "artifacts", "weight_ablation.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    main()