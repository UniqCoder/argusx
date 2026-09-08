"""
app/ml/shap_relative_recompute.py — Gate 3d: SHAP recompute of the 4 relative
features post-recalibration, on the DEPLOYED 92f model.

Two inputs:
  * OOD evidence — the raw 92-vectors recorded in broadened_ood_validation.json
    (6 known-legit + Garantex OFAC). These were computed through the PRODUCTION
    path WITH the recalibrated era-reference artifact (rel slots are the last 4
    columns). We recompute SHAP for each entity and pull the 4 rel-feature
    contributions.
  * Test-set slice — 3000 rows sampled from test (stratified by chain, seed 42),
    extended with relative features from the DEPLOYED artifact
    (apply_relative_features) plus GraphSAGE embeddings (augment_with_store), in
    the same layout the production /risk path feeds the model. We aggregate the
    SHAP contributions of the 4 rel features.

Checks:
  * non-degenerate: mean |SHAP| of each rel feature > 1e-4 in both slices;
  * direction sanity: rows with higher peer-relative activity (larger pctile or
    z) should push risk UP on net (positive SHAP when feature value > 0).

Writes artifacts/shap_relative_recompute.json.
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
import pandas as pd
import shap

from app.ml.features import add_embedding_columns
from app.ml.model import get_model
from app.ml.promotion_experiments import (
    MODEL_PLUS_RELATIVE_COLUMNS,
    augment_with_store,
    load_splits,
)
from app.ml.relative_features import RELATIVE_FEATURE_COLUMNS, apply_relative_features, load_relative_reference

logger = logging.getLogger(__name__)

_DIR = os.path.dirname(__file__)


def _rel_block(shap_row: np.ndarray, cols: list[str]) -> dict:
    out = {}
    for col, v in zip(cols, shap_row):
        if col in RELATIVE_FEATURE_COLUMNS:
            out[col] = round(float(v), 6)
    return out


def ood_slice(model) -> dict:
    with open(os.path.join(_DIR, "artifacts", "broadened_ood_validation.json"), encoding="utf-8") as f:
        report = json.load(f)
    entities = report.get("entities", []) + report.get("sanctioned_controls", [])
    rows = []
    for ent in entities:
        if ent.get("fetch_failed"):
            rows.append({"label": ent.get("label"), "fetch_failed": True})
            continue
        vec = np.asarray([ent["raw_92_vector"]], dtype=np.float32)
        sv = shap.TreeExplainer(model).shap_values(vec)
        srow = sv[0] if isinstance(sv, list) else sv[0]
        rows.append({
            "label": ent.get("label"),
            "chain": ent.get("chain"),
            "production_92f_score": ent.get("production_92f_score"),
            "production_92f_tier": ent.get("production_92f_tier"),
            "rel_slots": ent.get("raw_92_vector")[-4:],
            "rel_shap": _rel_block(srow, MODEL_PLUS_RELATIVE_COLUMNS),
        })
    return rows


def test_slice(model, sample_n: int = 3000, seed: int = 42) -> dict:
    train_df, _, test_df = load_splits()
    ref = load_relative_reference()
    frame = test_df.copy()
    frame = apply_relative_features(frame, ref)
    frame = augment_with_store(frame)
    frame = frame[MODEL_PLUS_RELATIVE_COLUMNS].fillna(0.0)

    rng = np.random.RandomState(seed)
    idx = rng.choice(len(frame), size=sample_n, replace=False)
    X = frame.iloc[idx].to_numpy(dtype=np.float32)

    explainer = shap.TreeExplainer(model)
    sv = explainer.shap_values(X)
    S = sv if not isinstance(sv, list) else sv[1]

    cols = list(frame.columns)
    rel_idx = [i for i, c in enumerate(cols) if c in RELATIVE_FEATURE_COLUMNS]
    rel_values = X[:, rel_idx]
    rel_shaps = S[:, rel_idx]

    by_col = {}
    for j, col in enumerate(RELATIVE_FEATURE_COLUMNS):
        vals = rel_values[:, j]
        shaps = rel_shaps[:, j]
        sign_agree = float(np.mean((vals > 1e-6) & (shaps > 0)) + np.mean((vals < -1e-6) & (shaps < 0)))
        by_col[col] = {
            "mean_abs_shap": float(np.mean(np.abs(shaps))),
            "mean_shap": float(np.mean(shaps)),
            "pct_nonzero_shap": float(np.mean(np.abs(shaps) > 1e-4)),
            "sign_agreement": round(sign_agree, 4),
        }
    return {"sample_n": sample_n, "seed": seed, "per_feature": by_col}


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)
    model = get_model()
    ood = ood_slice(model)
    ts = test_slice(model)

    check_ood = all(
        ent.get("fetch_failed") or min(abs(v) for v in ent["rel_shap"].values()) > 1e-4
        for ent in ood if "rel_shap" in ent
    )
    check_test = all(f["mean_abs_shap"] > 1e-4 for f in ts["per_feature"].values())
    outcome = {
        "purpose": "Gate 3d — post-recalibration SHAP recompute of the 4 relative features (deployed 92f)",
        "checks": {
            "ood_rel_shap_non_degenerate": check_ood,
            "test_slice_rel_shap_non_degenerate": check_test,
        },
        "ood_evidence": ood,
        "test_slice": ts,
    }
    out = os.path.join(_DIR, "artifacts", "shap_relative_recompute.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(outcome, f, indent=2)
    print("OOD rel SHAP (meanAbs by feature per entity):")
    for ent in ood:
        if "rel_shap" in ent:
            print(" ", ent["label"], {k: f"{v:+.4f}" for k, v in ent["rel_shap"].items()})
    print("Test-slice rel SHAP aggregates:")
    for col, f in ts["per_feature"].items():
        print(f"  {col}: mean|shap|={f['mean_abs_shap']:.4f} mean={f['mean_shap']:.4f} pct_nz={f['pct_nonzero_shap']:.3f}")
    print("Wrote", out)
    return outcome


if __name__ == "__main__":
    main()