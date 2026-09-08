"""
app/ml/rebuild_relative_reference.py — Pass 2: era-reference recalibration.

Builds a NEW relative-feature era reference by:
  1. Keeping the 8 original bin edges (from the Pass-1 artifact) byte-identical.
  2. Recomputing per-bin peer statistics (percentile_0.90 / median / mean / std)
     from the Elliptic UNLABELED BTC census (data/processed/btc_unlabeled.csv,
     ~557k real addresses, blocks 391200-487975) instead of the sparse Elliptic
     *train* rows (median 1 tx) that saturated every live wallet.
  3. Appending ONE modern bin [447655 -> 900000] whose peer statistics come
     from the harvested modern-era address census
     (artifacts/modern_era_address_census.json, born 841k-900k).

The JSON schema is UNCHANGED, so the runtime apply path
(app/ml/relative_features.py) needs zero code edits. Only the reference
distribution changes — the documented Pass-2 era calibration.

The apply math (relative_features.py) stays bit-identical to the validated
harness; relative_features_equivalence_check.py verifies apply-math parity.

Usage:
  python -m app.ml.rebuild_relative_reference
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)
ARTIFACTS = os.path.join(_DIR, "artifacts")
REFERENCE_PATH = os.path.join(ARTIFACTS, "relative_features_reference.json")
CENSUS_PATH = os.path.join(ARTIFACTS, "modern_era_address_census.json")
# Path resolution: running from backend/repo root both work.
for _cand in ("data/processed/btc_unlabeled.csv", "/app/data/processed/btc_unlabeled.csv", "../data/processed/btc_unlabeled.csv"):
    if os.path.exists(_cand):
        UNLABELED_PATH = _cand
        break
else:
    UNLABELED_PATH = "data/processed/btc_unlabeled.csv"

MODERN_EDGE = 900000.0
METRICS = ("total_txs", "value_transacted_total")


def _bin_stats(values: np.ndarray) -> dict:
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return {"percentile_0.90": 0.0, "median": 0.0, "mean": 0.0, "std": None}
    s = float(np.std(v))
    return {
        "percentile_0.90": float(np.quantile(v, 0.90)),
        "median": float(np.median(v)),
        "mean": float(np.mean(v)),
        "std": s if np.isfinite(s) and s > 0 else None,
    }


def main() -> None:
    # 1. Preserve ORIGINAL bin edges verbatim from the Pass-1 artifact.
    orig = json.load(open(REFERENCE_PATH, encoding="utf-8"))
    original_edges = [float(e) for e in orig["era_bin_edges"]]
    if not backup(REFERENCE_PATH, orig):
        return

    # 2. Unlabeled BTC census for historical-era peer stats.
    unlabeled = pd.read_csv(UNLABELED_PATH)
    sub = unlabeled[["first_block_appeared_in", "total_txs", "value_transacted_total"]].dropna(
        subset=["first_block_appeared_in"]
    )
    sub["first_block_appeared_in"] = sub["first_block_appeared_in"].astype(float)

    # 3. Modern-era census.
    census_meta = json.load(open(CENSUS_PATH, encoding="utf-8"))
    census_rows = pd.DataFrame(census_meta["addresses"])

    # Bin layout: historical bins = original_edges (9 edges, 8 bins); append the
    # modern bin [last_original_edge -> MODERN_EDGE] => 10 edges, 9 bins.
    bin_breaks = original_edges + [MODERN_EDGE]
    n_hist = len(original_edges) - 1  # 8 historical bins

    ref_metrics: dict[str, dict] = {}
    for metric in METRICS:
        hist = []
        for i in range(n_hist):
            lo, hi = original_edges[i], original_edges[i + 1]
            vals = sub.loc[
                (sub["first_block_appeared_in"] >= lo) & (sub["first_block_appeared_in"] < hi), metric
            ].to_numpy(dtype=float)
            b = _bin_stats(vals)
            # std not used per-bin (scalar std below), keep for reporting
            hist.append(b)

        modern_vals = census_rows[metric].to_numpy(dtype=float)
        modern = _bin_stats(modern_vals)

        # A bin with no rows keeps the prior value so percentile/median/mean are
        # always length == 9 (never empty gaps inside the scheduled layout).
        p90 = [b["percentile_0.90"] for b in hist] + [modern["percentile_0.90"]]
        med = [b["median"] for b in hist] + [modern["median"]]
        mean = [b["mean"] for b in hist] + [modern["mean"]]
        stds = [b["std"] for b in hist] + [modern["std"]]
        std_scalar = float(np.mean([s for s in stds if s is not None])) if any(s is not None for s in stds) else 1.0
        std_scalar = std_scalar if np.isfinite(std_scalar) and std_scalar > 0 else 1.0

        ref_metrics[metric] = {
            "percentile_0.90": [float(v) for v in p90],
            "median": [float(v) for v in med],
            "mean": [float(v) for v in mean],
            "std": std_scalar,
        }

    new_ref = {
        "era_bin_edges": [float(e) for e in bin_breaks],
        "train_max_block": MODERN_EDGE,
        "metrics": ref_metrics,
        "fit_scope": (
            "RECALIBRATED (Pass 2): historical bins keep the original 8 edges & bin structure; "
            "peer stats recomputed on Elliptic UNLABELED BTC census "
            f"({os.path.basename(UNLABELED_PATH)}, 391200-487975, ~557k real addresses) so "
            "percentiles reflect real-address activity; one modern bin [447655-900000] appended "
            f"from point-in-time modern census (artifacts/modern_era_address_census.json, "
            f"harvest {census_meta['harvest_date']}, born 841983-894823, n={len(census_rows)}). "
            "Apply math identical to validated harness; fit population intentionally differs from training fit."
        ),
        "pass2_recalibration": {
            "historical_bin_source": "data/processed/btc_unlabeled.csv",
            "modern_bin_source": "artifacts/modern_era_address_census.json",
            "modern_bin_high_edge": MODERN_EDGE,
            "rebuilt_utc": datetime.now(timezone.utc).isoformat(),
            "original_train_max_block": orig.get("train_max_block"),
        },
    }

    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_ref, f, indent=2)

    print(f"Wrote recalibrated reference -> {REFERENCE_PATH}")
    print(f"bin edges: {new_ref['era_bin_edges']}")
    for metric in METRICS:
        m = ref_metrics[metric]
        print(f"{metric}: p90={m['percentile_0.90']} median={m['median']} mean={m['mean']} std={m['std']:.4f}")


def backup(path: str, data: dict) -> bool:
    backup_path = path.replace(".json", ".pass1_backup.json")
    if not os.path.exists(backup_path):
        with open(backup_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        logger.info("pass1_reference_backed_up", extra={"path": backup_path})
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()