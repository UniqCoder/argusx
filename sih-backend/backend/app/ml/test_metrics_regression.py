"""
app/ml/test_metrics_regression.py — Gate 3c: test-set metric regression check.

Part A — Locked eval reproduction. Re-runs the exact promoted combined config
(run_combined_relative_tuned, scale_pos_weight=1.0, weight_mode="chain",
deterministic random_state=42) and compares BTC/ETH test AUC-PR and recall to
the LOCKED prerelease record (weight_ablation.json arm B):
    BTC AUC-PR 0.4666235346  recall 0.3910
    ETH AUC-PR 0.9717802188  recall 0.8567
Tolerance: 0.005 AUC-PR, 0.01 recall (same as weight_ablation). This config's
reference is re-fit on BTC train inside the harness, so the recalibrated
reference artifact CANNOT move it — a drift here would mean environment/data
regression, not era-reference change.

Part B — Deployed-artifact parity diagnostic. Compares the RELATIVE feature
values the deployed artifact (relative_features_reference.json, recalibrated in
Pass 2) yields on every train/val/test row vs the eval harness train-fit
reference. A zero max|diff| means production inference is bit-identical to the
eval's relative features for in-era rows. Non-zero (but small) diffs indicate
the intentional peer-population swap (train-labeled pool -> unlabeled
historical pool) documented in Pass 2; AUC-PR is unaffected because the eval
path re-fits its own reference.

Writes artifacts/test_metrics_regression.json.
"""
from __future__ import annotations

import json
import logging
import os
import sys

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

import numpy as np

from app.ml.promotion_experiments import (
    add_relative_features as harness_add,
    build_relative_feature_reference as harness_fit,
    load_splits,
    run_combined_relative_tuned,
)
from app.ml.relative_features import apply_relative_features as new_add

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
REL_COLS = [
    "total_txs_pctile_era", "value_transacted_total_pctile_era",
    "total_txs_z_era", "value_transacted_total_z_era",
]

LOCKED = {
    "btc": {"auc_pr": 0.4666235346417487, "recall": 0.3910490076954232, "threshold": 0.7},
    "eth": {"auc_pr": 0.9717802188196027, "recall": 0.8567073170731707},
}
TOL_AUC_PR = 0.005
TOL_RECALL = 0.01


def part_a(train_df, val_df, test_df) -> dict:
    res = run_combined_relative_tuned(
        train_df, val_df, test_df,
        scale_pos_weight=1.0, weight_mode="chain", return_probs=True,
    )
    b, e = res["btc_test"], res["eth_test"]
    checks = {
        "btc_auc_pr": {
            "actual": b["auc_pr"], "locked": LOCKED["btc"]["auc_pr"],
            "pass": abs(b["auc_pr"] - LOCKED["btc"]["auc_pr"]) <= TOL_AUC_PR,
        },
        "btc_recall": {
            "actual": b["recall"], "locked": LOCKED["btc"]["recall"],
            "pass": abs(b["recall"] - LOCKED["btc"]["recall"]) <= TOL_RECALL,
        },
        "eth_auc_pr": {
            "actual": e["auc_pr"], "locked": LOCKED["eth"]["auc_pr"],
            "pass": abs(e["auc_pr"] - LOCKED["eth"]["auc_pr"]) <= TOL_AUC_PR,
        },
        "eth_recall": {
            "actual": e["recall"], "locked": LOCKED["eth"]["recall"],
            "pass": abs(e["recall"] - LOCKED["eth"]["recall"]) <= TOL_RECALL,
        },
        "threshold_locked": {
            "actual": res["threshold"], "locked": LOCKED["btc"]["threshold"],
            "pass": res["threshold"] == LOCKED["btc"]["threshold"],
        },
    }
    print(f"[A] thr={res['threshold']} BTC AUC-PR={b['auc_pr']:.4f} rec={b['recall']:.4f} "
          f"ETH AUC-PR={e['auc_pr']:.4f} rec={e['recall']:.4f}")
    return {"checks": checks, "btc_test": b, "eth_test": e}


def part_b(train_df, val_df, test_df) -> dict:
    from app.ml.relative_features import load_relative_reference
    btc_train = train_df[train_df["chain"].astype(str) == "BTC"].copy()
    harness_ref = harness_fit(btc_train)
    deployed_ref = load_relative_reference()

    splits = []
    for split_name, frame in (("train", train_df), ("val", val_df), ("test", test_df)):
        h = harness_add(frame, harness_ref)
        d = new_add(frame, deployed_ref)
        maxfb = float(frame["first_block_appeared_in"].max())
        diffs = []
        for col in REL_COLS:
            a = h[col].to_numpy(dtype=float)
            b = d[col].to_numpy(dtype=float)
            md = float(np.max(np.abs(a - b))) if len(a) else 0.0
            diffs.append({"col": col, "max_abs_diff": md})
        splits.append({"split": split_name, "max_first_block": maxfb, "diffs": diffs,
                       "any_diff_gt_0": any(x["max_abs_diff"] > 0 for x in diffs)})
        print(f"[B] {split_name:5s} max_block={maxfb:.0f} "
              f"max|diff|={max(d['max_abs_diff'] for d in diffs):.3e} "
              f"nonzero_any={splits[-1]['any_diff_gt_0']}")
    return {
        "harness_ref_fit_scope": "build_relative_feature_reference(btc_train)",
        "deployed_ref_path": os.path.join(_DIR, "artifacts", "relative_features_reference.json"),
        "splits": splits,
    }


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    train_df, val_df, test_df = load_splits()
    a = part_a(train_df, val_df, test_df)
    b = part_b(train_df, val_df, test_df)
    part_a_pass = all(c["pass"] for c in a["checks"].values())
    outcome = {
        "purpose": "Gate 3c — locked test-set metric regression (Pass 2 recalibration)",
        "tolerances": {"auc_pr": TOL_AUC_PR, "recall_pp": TOL_RECALL},
        "part_a_locked_eval_reproduction": a,
        "part_a_pass": part_a_pass,
        "part_b_deployed_artifact_parity_diagnostic": b,
        "overall": "PASS — locked eval reproduces within tolerance" if part_a_pass
                   else "FAIL — locked eval drifted",
    }
    out = os.path.join(_DIR, "artifacts", "test_metrics_regression.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(outcome, f, indent=2)
    print("PART A PASS =", part_a_pass)
    print("Wrote", out)
    return outcome


if __name__ == "__main__":
    main()