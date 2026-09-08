"""
app/ml/promotion_experiments.py — Targeted, low-risk 88-feature model improvements.

Runs three offline experiments against the PRODUCTION baseline (BTC AUC-PR 0.427,
recall 38%) on the SAME data/processed splits and SAME precomputed GraphSAGE
embedding store as `train.py::train_combined_model` so results are apples-to-apples:

  Task 1: entity-scale-relative features (percentile / z-score vs same-era peers)
          as an additive superset (88f + new cols). Offline BTC metrics are the
          promotion gate; live Satoshi/ETH-Foundation scoring is a separate
          diagnostic run via risk_service.
  Task 3: Optuna hyperparameter search (learning_rate, max_depth, n_estimators,
          scale_pos_weight) on the 88-feature input, keeping production per-chain
          sample-weights.
  Task 4: SMOTE / borderline-SMOTE oversampling on the BTC training subset only,
          compared against baseline and against scale_pos_weight-only.

Promotion rule (from docs/ml.md operating point): only promote a config whose
offline BTC AUC-PR / recall improves or holds steady vs 0.427 / 38% AND whose
combined-validation FPR stays below the 2% cap at the locked threshold.

This module never mutates the deployed 88-column schema (MODEL_FEATURE_COLUMNS /
assert_model_feature_schema); new feature columns live only inside experimental
matrices until a config is actually promoted.
"""
from __future__ import annotations

import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    precision_recall_curve,
    roc_auc_score,
)

logger = logging.getLogger(__name__)

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.features import (
    FEATURE_COLUMNS,
    GSAGE_EMBEDDING_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    assert_model_feature_schema,
)
from app.ml.embedding_store import lookup_embedding
from app.ml.train import (
    ARTIFACTS_DIR,
    get_processed_dir,
    select_best_threshold,
)

# ── Relative-feature schema (Task 1) ─────────────────────────────────────────
# Appended to the 72 tabular/graph features + 16 embeddings -> 88 + these.
RELATIVE_FEATURE_COLUMNS: list[str] = [
    "total_txs_pctile_era",
    "value_transacted_total_pctile_era",
    "total_txs_z_era",
    "value_transacted_total_z_era",
]

# Full 92-col schema for the combined experiment harness. MODEL_FEATURE_COLUMNS
# ALREADY includes the 4 relative features (72 + 16 + 4 = 92); re-appending
# RELATIVE_FEATURE_COLUMNS here would create duplicated XGBoost feature names
# and break trainer/predictor ("feature_names must be unique").
MODEL_PLUS_RELATIVE_COLUMNS: list[str] = list(MODEL_FEATURE_COLUMNS)


# ── Shared data loading / augmentation ───────────────────────────────────────
def load_splits(processed_dir: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    processed_dir = processed_dir or get_processed_dir()
    train_df = pd.read_csv(os.path.join(processed_dir, "train.csv"))
    val_df = pd.read_csv(os.path.join(processed_dir, "val.csv"))
    test_df = pd.read_csv(os.path.join(processed_dir, "test.csv"))
    return train_df, val_df, test_df


def augment_with_store(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the 16 GraphSAGE cols from the precomputed store (matches production)."""
    frame = frame.copy()
    emb_cols = np.zeros((len(frame), len(GSAGE_EMBEDDING_COLUMNS)), dtype=np.float32)
    for i, addr in enumerate(frame["address"].astype(str)):
        emb_cols[i] = lookup_embedding(addr)
    for dim in range(len(GSAGE_EMBEDDING_COLUMNS)):
        frame[GSAGE_EMBEDDING_COLUMNS[dim]] = emb_cols[:, dim]
    return frame


THRESHOLD_CANDIDATES = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]


def _eval(labels: pd.Series, probs: np.ndarray, threshold: float) -> dict:
    preds = (probs >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, preds).ravel()
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)
    return {
        "rows": int(len(labels)),
        "threshold": float(threshold),
        "precision": float(precision),
        "recall": float(recall),
        "fpr": float(fpr),
        "auc_pr": float(average_precision_score(labels, probs)),
        "auc_roc": float(roc_auc_score(labels, probs)),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def _btc_eval(test_df: pd.DataFrame, probs: np.ndarray, threshold: float) -> dict:
    mask = (test_df["chain"].astype(str) == "BTC").to_numpy()
    return _eval(test_df.loc[mask, "label"], probs[mask], threshold)


def base_xgb_kwargs() -> dict:
    return {
        "n_estimators": 150,
        "max_depth": 5,
        "learning_rate": 0.06,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "eval_metric": "logloss",
        "random_state": 42,
        "tree_method": "hist",
    }


# ── Baseline reproduction (must hit BTC AUC-PR 0.427 / recall 38%) ───────────
def run_baseline(train_df: pd.DataFrame, val_df: pd.DataFrame, test_df: pd.DataFrame,
                 feature_cols: list[str] | None = None, sample_weights: np.ndarray | None = None) -> dict:
    feature_cols = feature_cols or MODEL_FEATURE_COLUMNS
    if sample_weights is None:
        sample_weights = train_df["sample_weight"].to_numpy()
    X_train = train_df[feature_cols].fillna(0.0)
    X_val = val_df[feature_cols].fillna(0.0)
    X_test = test_df[feature_cols].fillna(0.0)

    clf = xgb.XGBClassifier(**base_xgb_kwargs())
    clf.fit(X_train, train_df["label"], sample_weight=sample_weights)
    val_prob = clf.predict_proba(X_val)[:, 1]
    threshold, val_summary = select_best_threshold(val_df["label"], val_prob, THRESHOLD_CANDIDATES)
    test_prob = clf.predict_proba(X_test)[:, 1]
    return {
        "clf": clf,
        "threshold": threshold,
        "val_summary": val_summary,
        "test_prob": test_prob,
        "combined_test": _eval(test_df["label"], test_prob, threshold),
        "btc_test": _btc_eval(test_df, test_prob, threshold),
    }


# ── Task 3: Optuna hyperparameter search on 88f, keeping sample weights ─────
def _objective(train_df, val_df, feature_cols, sample_weights, trial):
    lr = trial.suggest_float("learning_rate", 0.02, 0.2, log=True)
    depth = trial.suggest_int("max_depth", 3, 8)
    n_est = trial.suggest_int("n_estimators", 100, 400)
    subsample = trial.suggest_float("subsample", 0.5, 1.0)
    colsample = trial.suggest_float("colsample_bytree", 0.5, 1.0)
    spw = trial.suggest_float("scale_pos_weight", 1.0, 40.0)  # 0 -> disabled

    kw = base_xgb_kwargs()
    kw.update(n_estimators=n_est, max_depth=depth, learning_rate=lr,
              subsample=subsample, colsample_bytree=colsample, scale_pos_weight=spw)
    clf = xgb.XGBClassifier(**kw)
    clf.fit(train_df[feature_cols].fillna(0.0), train_df["label"], sample_weight=sample_weights)
    val_prob = clf.predict_proba(val_df[feature_cols].fillna(0.0))[:, 1]
    return float(average_precision_score(val_df["label"], val_prob))  # maximize combined-val AUC-PR


def run_optuna_tuning(train_df, val_df, test_df, n_trials: int = 40, seed: int = 42,
                      best_params: dict | None = None) -> dict:
    import optuna
    feature_cols = MODEL_FEATURE_COLUMNS
    sample_weights = train_df["sample_weight"].to_numpy()

    if best_params is None:
        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
        study.optimize(lambda trial: _objective(train_df, val_df, feature_cols, sample_weights, trial),
                       n_trials=n_trials, show_progress_bar=False)
        best = study.best_params
        best_val = study.best_value
        logger.info("[Task 3] Optuna best params: %s  (val AUC-PR %.4f)", best, best_val)
        _best_auc_pr = float(best_val)
    else:
        best = best_params
        _best_auc_pr = None
        logger.info("[Task 3] Using precomputed best params: %s", best)

    kw = base_xgb_kwargs()
    kw.update(n_estimators=best["n_estimators"], max_depth=best["max_depth"],
              learning_rate=best["learning_rate"], subsample=best["subsample"],
              colsample_bytree=best["colsample_bytree"], scale_pos_weight=best["scale_pos_weight"])
    clf = xgb.XGBClassifier(**kw)
    clf.fit(train_df[feature_cols].fillna(0.0), train_df["label"], sample_weight=sample_weights)
    val_prob = clf.predict_proba(val_df[feature_cols].fillna(0.0))[:, 1]
    threshold, val_summary = select_best_threshold(val_df["label"], val_prob, THRESHOLD_CANDIDATES)
    test_prob = clf.predict_proba(test_df[feature_cols].fillna(0.0))[:, 1]
    return {
        "best_params": best,
        "best_val_auc_pr": _best_auc_pr,
        "threshold": threshold,
        "val_summary": val_summary,
        "combined_test": _eval(test_df["label"], test_prob, threshold),
        "btc_test": _btc_eval(test_df, test_prob, threshold),
    }


# ── Task 4: SMOTE / borderline-SMOTE on BTC training subset only ────────────
def smote_weights_experiments(train_df, val_df, test_df) -> dict:
    from imblearn.over_sampling import SMOTE, BorderlineSMOTE

    feature_cols = MODEL_FEATURE_COLUMNS
    # Recompute per-chain weights on the (possibly oversampled) frame.
    from app.ml.train import build_per_chain_sample_weights

    results: dict = {}
    specs = {
        "smote_borderline": BorderlineSMOTE(random_state=42, k_neighbors=5),
        "smote_vanilla": SMOTE(random_state=42, k_neighbors=5),
    }

    for name, resampler in specs.items():
        btc_mask = (train_df["chain"].astype(str) == "BTC").to_numpy()
        btc_idx = np.where(btc_mask)[0]

        # SMOTE ONLY the BTC rows (88-col matrix: tabular + embeddings). Synthetic
        # rows are feature-space interpolations; embeddings are interpolated just
        # like any other column, which is consistent with SMOTE semantics. ETH rows
        # are left entirely untouched (different imbalance profile, per spec).
        X_btc = train_df.loc[btc_idx, feature_cols].fillna(0.0)
        y_btc = train_df.loc[btc_idx, "label"].to_numpy()
        logger.info("[Task 4] %s on BTC train: %d rows (%d illicit) -> ...", name, len(X_btc), int(y_btc.sum()))
        X_res, y_res = resampler.fit_resample(X_btc, y_btc)
        logger.info("[Task 4] %s -> %d rows (%d illicit)", name, len(X_res), int((y_res == 1).sum()))

        new_rows = X_res.copy()
        new_rows["address"] = "smote_synth"
        new_rows["chain"] = "BTC"
        new_rows["label"] = y_res

        # Combine resampled BTC block with original ETH rows (already augmented
        # with embeddings when loaded into run_all).
        eth_rows = train_df[~btc_mask].copy()
        combined_train = pd.concat([new_rows, eth_rows], ignore_index=True, sort=False)
        combined_train = _ensure_columns(combined_train, feature_cols)
        combined_train["chain"] = combined_train["chain"].astype(str)

        # Recompute per-chain sample weights on the oversampled frame.
        weights = build_per_chain_sample_weights(combined_train)
        sample_weights = np.zeros(len(combined_train))
        for chain, idxs in combined_train.groupby("chain").groups.items():
            idx_arr = np.asarray(list(idxs))
            sample_weights[idx_arr] = weights[idx_arr]

        res = run_baseline(combined_train, val_df, test_df, feature_cols=feature_cols,
                           sample_weights=sample_weights)
        results[name] = {
            "oversampled_btc_rows": int(len(X_res)),
            "btc_illicit_after": int((y_res == 1).sum()),
            "threshold": res["threshold"],
            "combined_test": res["combined_test"],
            "btc_test": res["btc_test"],
        }
    return results


def _ensure_columns(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    for c in cols:
        if c not in frame.columns:
            frame[c] = 0.0
    return frame


# ── Task 1: entity-scale-relative features ──────────────────────────────────
def build_relative_feature_reference(train_btc: pd.DataFrame) -> dict:
    """Fit era-bucket references (percentile / mean+std) on BTC TRAIN rows ONLY."""
    train_btc = train_btc.copy()
    era_bins = pd.qcut(train_btc["first_block_appeared_in"], q=8, duplicates="drop")
    train_btc["_era_bin"] = era_bins
    bins = list(era_bins.cat.categories)
    ref = {}
    for metric in ("total_txs", "value_transacted_total"):
        g = train_btc.groupby("_era_bin", observed=True)[metric]
        ref[metric] = {
            "bins": bins,
            "percentile": g.quantile(0.90).to_dict(),
            "median": g.median().to_dict(),
            "mean": g.mean().to_dict(),
            "std": g.std().to_numpy().mean() or 1.0,
        }
    return ref


def add_relative_features(frame: pd.DataFrame, ref: dict) -> pd.DataFrame:
    """Compute relative features; OOD era values map to the top training bin."""
    frame = frame.copy()
    fb = frame["first_block_appeared_in"].to_numpy()
    train_max = max(cat.right for cat in ref["total_txs"]["bins"])

    # Era bin index: the qcut categories are open intervals; map any block value
    # > training max to the last (highest) bin.
    def era_idx(v: float):
        finite = np.isfinite(v)
        vv = np.clip(v, -np.inf, train_max) if finite else train_max
        for i, cat in enumerate(ref["total_txs"]["bins"]):
            if cat.left <= vv < cat.right:
                return i
        return len(ref["total_txs"]["bins"]) - 1 if finite else -1

    b_idx = np.array([era_idx(v) for v in fb])
    for metric in ("total_txs", "value_transacted_total"):
        p90 = np.array([list(ref[metric]["percentile"].values())[i] if 0 <= i < len(ref[metric]["bins"]) else 0.0 for i in b_idx])
        med = np.array([list(ref[metric]["median"].values())[i] if 0 <= i < len(ref[metric]["bins"]) else 0.0 for i in b_idx])
        mean = np.array([list(ref[metric]["mean"].values())[i] if 0 <= i < len(ref[metric]["bins"]) else 0.0 for i in b_idx])
        std = ref[metric]["std"]
        vals = frame[metric].to_numpy(dtype=float)
        pctile = np.where(p90 > 0, np.clip(vals / np.maximum(p90, 1e-12), 0.0, 1.0), 0.0)
        z = np.where(std > 0, (vals - mean) / std, 0.0)
        frame[f"{metric}_pctile_era"] = np.nan_to_num(pctile, nan=0.0)
        frame[f"{metric}_z_era"] = np.nan_to_num(z, nan=0.0)
    return frame


def run_relative_feature_experiment(train_df, val_df, test_df, processed_dir: str | None = None) -> dict:
    """Task 1: additive relative features (88 -> 92) on BTC training reference.

    Primary promotion gate = offline BTC test AUC-PR / recall vs baseline.
    """
    # Fit reference ONLY on BTC train rows.
    btc_train = train_df[train_df["chain"].astype(str) == "BTC"].copy()
    ref = build_relative_feature_reference(btc_train)

    def transform(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame = add_relative_features(frame, ref)
        frame = augment_with_store(frame)
        return _ensure_columns(frame, MODEL_PLUS_RELATIVE_COLUMNS)

    tr = transform(train_df)
    va = transform(val_df)
    te = transform(test_df)

    sample_weights = train_df["sample_weight"].to_numpy()
    res = run_baseline(tr, va, te, feature_cols=MODEL_PLUS_RELATIVE_COLUMNS,
                       sample_weights=sample_weights)
    return {
        "clf": res["clf"],
        "reference": ref,
        "feature_count": len(MODEL_PLUS_RELATIVE_COLUMNS),
        "relative_features": RELATIVE_FEATURE_COLUMNS,
        "reference_fit_scope": "BTC train rows only (time_step<=29); era-qcut q=8",
        "ood_era_mapping": "block > train-max mapped to top train bin (extrapolated ref)",
        "threshold": res["threshold"],
        "combined_test": res["combined_test"],
        "btc_test": res["btc_test"],
    }


# ── Orchestration ────────────────────────────────────────────────────────────
def run_combined_relative_tuned(train_df, val_df, test_df,
                                tuned_params: dict | None = None,
                                processed_dir: str | None = None,
                                return_probs: bool = False,
                                scale_pos_weight: float | None = None,
                                weight_mode: str = "chain") -> dict:
    """Task 1 + Task 3 combined: relative features AND tuned HPs on 92-col input.

    This is the strongest candidate: the Optuna-tuned HPs recover recall that
    Task 1's relative features gave up, while relative features add AUC-PR.

    ``scale_pos_weight`` overrides the tuned value (weight-ablation arms); when
    None the tuned 4.93 is used. ``weight_mode`` chooses the per-sample weight
    source: "chain" = production per-chain sample_weight (train.csv), "uniform"
    = all-ones (removes chain mass balancing to isolate the mechanism).
    """
    tuned_params = tuned_params or {
        "learning_rate": 0.11111992920245407,
        "max_depth": 7,
        "n_estimators": 292,
        "subsample": 0.9172272185207363,
        "colsample_bytree": 0.7571088996592841,
        "scale_pos_weight": 4.931116282851712,
    }
    btc_train = train_df[train_df["chain"].astype(str) == "BTC"].copy()
    ref = build_relative_feature_reference(btc_train)

    def transform(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame = add_relative_features(frame, ref)
        frame = augment_with_store(frame)
        return _ensure_columns(frame, MODEL_PLUS_RELATIVE_COLUMNS)

    tr = transform(train_df)
    va = transform(val_df)
    te = transform(test_df)

    if weight_mode == "uniform":
        sample_weights = np.ones(len(train_df), dtype=np.float32)
    else:
        sample_weights = train_df["sample_weight"].to_numpy()
    feature_cols = MODEL_PLUS_RELATIVE_COLUMNS

    kw = base_xgb_kwargs()
    kw.update(n_estimators=tuned_params["n_estimators"], max_depth=tuned_params["max_depth"],
              learning_rate=tuned_params["learning_rate"], subsample=tuned_params["subsample"],
              colsample_bytree=tuned_params["colsample_bytree"],
              scale_pos_weight=tuned_params["scale_pos_weight"]
              if scale_pos_weight is None else scale_pos_weight)
    clf = xgb.XGBClassifier(**kw)
    clf.fit(tr[feature_cols].fillna(0.0), train_df["label"], sample_weight=sample_weights)
    val_prob = clf.predict_proba(va[feature_cols].fillna(0.0))[:, 1]
    threshold, val_summary = select_best_threshold(val_df["label"], val_prob, THRESHOLD_CANDIDATES)
    test_prob = clf.predict_proba(te[feature_cols].fillna(0.0))[:, 1]

    out = {
        "clf": clf,
        "reference": ref,
        "feature_count": len(feature_cols),
        "hyperparameters": tuned_params,
        "threshold": threshold,
        "val_summary": val_summary,
        "combined_test": _eval(test_df["label"], test_prob, threshold),
        "btc_test": _btc_eval(test_df, test_prob, threshold),
        "eth_test": _eth_eval(test_df, test_prob, threshold),
    }
    if return_probs:
        out["val_prob"] = val_prob
        out["test_prob"] = test_prob
    return out


def _eth_eval(test_df: pd.DataFrame, probs: np.ndarray, threshold: float) -> dict:
    mask = (test_df["chain"].astype(str) == "ETH").to_numpy()
    return _eval(test_df.loc[mask, "label"], probs[mask], threshold)


def run_all(processed_dir: str | None = None, n_trials: int = 40) -> dict:
    train_df, val_df, test_df = load_splits(processed_dir)
    logger.info("Augmenting train/val/test with precomputed embeddings...")
    train_df = augment_with_store(train_df)
    val_df = augment_with_store(val_df)
    test_df = augment_with_store(test_df)

    report = {"splits": {"train": int(len(train_df)), "val": int(len(val_df)), "test": int(len(test_df))}}

    logger.info("Running baseline reproduction...")
    base = run_baseline(train_df, val_df, test_df)
    report["baseline_production_rep"] = {
        "threshold": base["threshold"],
        "combined_test": base["combined_test"],
        "btc_test": base["btc_test"],
    }

    report["task1_relative_features"] = run_relative_feature_experiment(train_df, val_df, test_df, processed_dir)

    logger.info("Running Task 3 Optuna tuning...")
    report["task3_optuna"] = run_optuna_tuning(train_df, val_df, test_df, n_trials=n_trials)

    logger.info("Running Task 4 SMOTE experiments...")
    report["task4_smote"] = smote_weights_experiments(train_df, val_df, test_df)

    out_path = os.path.join(ARTIFACTS_DIR, "promotion_experiments.json")
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info("Wrote %s", out_path)
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    report = run_all()
    print(json.dumps(report, indent=2))
