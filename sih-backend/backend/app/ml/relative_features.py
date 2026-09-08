"""
app/ml/relative_features.py — Entity-scale-relative features (promoted config).

The validated config extends the 88-feature model with 4 relative features that
benchmark a wallet's transaction count / transacted value against same-era peers:

  total_txs_pctile_era, value_transacted_total_pctile_era,
  total_txs_z_era, value_transacted_total_z_era

The era reference (percentile/mean/std per first-block era bucket) is fit ONCE on
BTC training rows only and persisted as a JSON artifact. Runtime inference loads
the artifact AS-IS so features are OOD-safe for fresh addresses (block values
outside the training era map to the newest training bin) and never re-fit on
request data.

The math here is bit-identical to the validated harness
(app/ml/promotion_experiments.py::build_relative_feature_reference /
add_relative_features). An equivalence check is part of the promotion verification
(backend/app/ml/relative_features_equivalence_check.py).
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RELATIVE_FEATURE_COLUMNS: list[str] = [
    "total_txs_pctile_era",
    "value_transacted_total_pctile_era",
    "total_txs_z_era",
    "value_transacted_total_z_era",
]

_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
REFERENCE_PATH = os.path.join(_ARTIFACTS_DIR, "relative_features_reference.json")

_RESERVED = object()
_cache = {"reference": _RESERVED}


def fit_relative_reference(btc_train: pd.DataFrame) -> dict:
    """Fit the era-bucket reference on BTC TRAIN rows ONLY (JSON-safe output).

    Mirrors ``promotion_experiments.build_relative_feature_reference``:
    ``pd.qcut(first_block_appeared_in, q=8, duplicates="drop")`` and per-bin
    p90 / median / mean plus a scalar std (mean of per-bin stds).
    """
    btc_train = btc_train.copy()
    era_bins = pd.qcut(btc_train["first_block_appeared_in"], q=8, duplicates="drop")
    btc_train["_era_bin"] = era_bins
    cats = list(era_bins.cat.categories)
    edges = [float(c.left) for c in cats] + [float(cats[-1].right)]
    ref: dict = {
        "era_bin_edges": edges,
        "train_max_block": float(max(c.right for c in cats)),
        "metrics": {},
        "fit_scope": "BTC train rows only (data/processed/train.csv, chain==BTC)",
    }
    for metric in ("total_txs", "value_transacted_total"):
        grouped = btc_train.groupby("_era_bin", observed=True)[metric]
        p90 = grouped.quantile(0.90).to_numpy(dtype=float)
        median = grouped.median().to_numpy(dtype=float)
        mean = grouped.mean().to_numpy(dtype=float)
        std_mean = float(np.mean(grouped.std().to_numpy(dtype=float))) if len(grouped) > 0 else 0.0
        std = std_mean if (np.isfinite(std_mean) and std_mean != 0.0) else 1.0  # matches `... or 1.0`
        ref["metrics"][metric] = {
            "percentile_0.90": [float(v) for v in p90],
            "median": [float(v) for v in median],
            "mean": [float(v) for v in mean],
            "std": float(std),
        }
    return ref


def save_relative_reference(ref: dict) -> str:
    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
    with open(REFERENCE_PATH, "w", encoding="utf-8") as f:
        json.dump(ref, f, indent=2)
    reset_reference_cache()
    logger.info("relative_features_reference_saved", extra={"path": REFERENCE_PATH})
    return REFERENCE_PATH


def load_relative_reference() -> Optional[dict]:
    """Lazily load the persisted reference once. Returns None when not present."""
    cached = _cache["reference"]
    if cached is not _RESERVED:
        return cached
    ref = None
    if os.path.exists(REFERENCE_PATH):
        try:
            with open(REFERENCE_PATH, encoding="utf-8") as f:
                ref = json.load(f)
        except Exception:  # noqa: BLE001 — corrupt artifact degrades to no-relative-features
            logger.exception("relative_features_reference_corrupt")
            ref = None
    _cache["reference"] = ref
    return ref


def reset_reference_cache() -> None:
    global _cache
    _cache = {"reference": _RESERVED}


def relative_reference_state() -> str:
    """Explicit artifact state for downstream logging:
      - "full"     loaded and schema-valid (relative features are real)
      - "fallback" artifact absent (relative features zeroed, expected)
      - "failed"   artifact present but unreadable/corrupt or schema-mismatched
                   (relative features zeroed AND this is an anomaly to surface)
    """
    ref = load_relative_reference()
    if ref is None:
        return "failed" if os.path.exists(REFERENCE_PATH) else "fallback"
    if not _bins_match_edges(ref):
        return "failed"
    return "full"


def _era_edges(ref: dict) -> tuple[list[float], float]:
    edges = [float(e) for e in ref["era_bin_edges"]]
    return edges, max(edges)


def _era_idx(block_value: float, edges: list[float]) -> int:
    """Return the era-bucket index for one block value (OOD-safe).

    Block values above the training max or below the first-era floor map to the
    newest training bin; non-finite values map to -1 (features become 0.0),
    matching the validated harness exactly.
    """
    if not np.isfinite(block_value):
        return -1
    vv = float(block_value)
    if vv > edges[-1]:
        vv = edges[-1]
    for i in range(len(edges) - 1):
        if edges[i] <= vv < edges[i + 1]:
            return i
    return len(edges) - 2  # last bin (len(edges) - 1 bins)


def _bins_match_edges(ref: dict) -> bool:
    edges, _ = _era_edges(ref)
    for metric in ref.get("metrics", {}):
        stats = ref["metrics"][metric]
        for key in ("percentile_0.90", "median", "mean"):
            if len(stats[key]) != len(edges) - 1:
                return False
    return True


def relative_features_for_wallet(feature_dict: dict, ref: Optional[dict]) -> dict[str, float]:
    """Compute the 4 relative features for one wallet's feature dict (live path).

    Matches the validated harness exactly, including the NaN/no-era case
    (era index -1): percentile feature 0.0, z-score = raw value / reference std.
    """
    zeros = {col: 0.0 for col in RELATIVE_FEATURE_COLUMNS}
    if ref is None or not _bins_match_edges(ref):
        return zeros
    edges, _ = _era_edges(ref)
    fb = feature_dict.get("first_block_appeared_in")
    idx = _era_idx(float(fb), edges) if fb is not None else -1
    out = {}
    for metric in ("total_txs", "value_transacted_total"):
        stats = ref["metrics"][metric]
        p90 = float(stats["percentile_0.90"][idx]) if idx >= 0 else 0.0
        mean = float(stats["mean"][idx]) if idx >= 0 else 0.0
        std = float(stats["std"])
        val = float(feature_dict.get(metric, 0.0) or 0.0)
        pctile = np.clip(val / max(p90, 1e-12), 0.0, 1.0) if p90 > 0 else 0.0
        z = (val - mean) / std if std > 0 else 0.0
        out[f"{metric}_pctile_era"] = float(np.nan_to_num(pctile, nan=0.0))
        out[f"{metric}_z_era"] = float(np.nan_to_num(z, nan=0.0))
    return out


def apply_relative_features(frame: pd.DataFrame, ref: Optional[dict]) -> pd.DataFrame:
    """Add the 4 relative-feature columns to a frame (training / offline path).

    Mirrors the validated harness ``add_relative_features`` bit-for-bit, incl.
    the era index -1 convention (non-finite block): percentile -> 0.0,
    z-score -> raw value / reference std.
    """
    frame = frame.copy()
    for col in RELATIVE_FEATURE_COLUMNS:
        frame[col] = 0.0
    if ref is None or not _bins_match_edges(ref):
        return frame
    edges, _ = _era_edges(ref)
    fb = frame["first_block_appeared_in"].to_numpy(dtype=float)
    idxs = np.array([_era_idx(v, edges) for v in fb], dtype=int)
    for metric in ("total_txs", "value_transacted_total"):
        stats = ref["metrics"][metric]
        p90 = np.array(stats["percentile_0.90"], dtype=float)
        mean = np.array(stats["mean"], dtype=float)
        std = float(stats["std"]) if float(stats["std"]) > 0 else 1.0
        p90_row = np.where(idxs >= 0, p90[np.clip(idxs, 0, len(p90) - 1)], 0.0)
        mean_row = np.where(idxs >= 0, mean[np.clip(idxs, 0, len(mean) - 1)], 0.0)
        vals = np.nan_to_num(frame[metric].to_numpy(dtype=float), nan=0.0)
        pctile = np.where(p90_row > 0, np.clip(vals / np.maximum(p90_row, 1e-12), 0.0, 1.0), 0.0)
        z = np.where(std > 0, (vals - mean_row) / std, 0.0)
        frame[f"{metric}_pctile_era"] = np.nan_to_num(pctile, nan=0.0)
        frame[f"{metric}_z_era"] = np.nan_to_num(z, nan=0.0)
    return frame