"""
app/ml/train_with_graph_features.py — Retrain XGBoost with engineered graph features.

Uses the EXACT SAME HYPERPARAMETERS as the production baseline:
  - n_estimators=150
  - scale_pos_weight=computed from training set
  - max_depth=5, learning_rate=0.06, subsample=0.85, colsample_bytree=0.85

The ONLY change is the input feature set (62 → 65 features: added 3 graph features).
This ensures any metric difference is attributable to the engineered graph features, not model configuration.
"""
import json
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import shap
import joblib

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
from sklearn.metrics import (
    confusion_matrix,
    average_precision_score,
    roc_auc_score,
    precision_score,
    recall_score,
)

from app.ml.features import FEATURE_COLUMNS, MISSING_INDICATOR_COLUMNS, GRAPH_FEATURE_COLUMNS, assert_feature_schema
from app.ml.train import (
    DATASET_TO_CANONICAL_RENAME,
    ARTIFACTS_DIR,
    select_best_threshold,
    get_data_dir,
    add_missing_indicators,
)
from app.ml.graph_features import compute_graph_features

logger = logging.getLogger(__name__)


def load_training_data_with_graph_features(
    data_dir: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Load Elliptic++ training data + computed graph features.
    
    Returns:
        - train_df: rows from time steps 1-29
        - val_df: rows from time steps 30-34
        - test_df: rows from time steps 35-49
        Each has all 65 features (62 tabular + 3 graph)
    """
    data_dir = data_dir or get_data_dir()
    
    # Load base features
    feature_path = os.path.join(data_dir, "wallets_features.csv")
    class_path = os.path.join(data_dir, "wallets_classes.csv")
    
    wallet_features = pd.read_csv(feature_path)
    wallet_classes = pd.read_csv(class_path)
    
    # Merge
    df = wallet_features.merge(wallet_classes[["address", "class"]], on="address", how="inner")
    df = df.drop_duplicates()  # remove exact-copy rows first
    df = df.drop_duplicates(subset=["address"], keep="last").copy()
    df = df[df["class"].isin([1, 2])].copy()
    df["label"] = (df["class"] == 1).astype(int)
    
    # Canonicalize to training feature schema
    canonical = df.rename(columns=DATASET_TO_CANONICAL_RENAME)
    missing = [column for column in FEATURE_COLUMNS if column not in canonical.columns]
    if missing:
        canonical = canonical.assign(**{column: np.nan for column in missing})
    # IMPORTANT: compute missing-indicator columns (matches baseline train.py path)
    canonical = add_missing_indicators(canonical)
    
    # Remove graph features from canonical before adding them back
    non_graph_cols = [c for c in FEATURE_COLUMNS if c not in GRAPH_FEATURE_COLUMNS]
    canonical = canonical[non_graph_cols + ["address", "label", "Time step", "class"]].copy()
    
    # Load graph features from the FULL graph (all time steps). Using only the training
    # period (time_step_threshold=29) would give 98% of test-set wallets all-zero graph
    # features because those wallets only first appear in later time steps, creating a
    # severe train/test distribution shift that masquerades as a negative finding.
    logger.info("Computing graph features from FULL AddrAddr_edgelist.csv (all time steps)...")
    graph_features_df = compute_graph_features(data_dir, time_step_threshold=None)
    graph_features_df["address"] = graph_features_df["address"].astype(str)
    graph_features_df = graph_features_df.drop_duplicates(subset=["address"], keep="last")
    
    # Merge graph features on 'address' (explicit key merge, NOT positional concat)
    canonical["address"] = canonical["address"].astype(str)
    assert not canonical.duplicated(subset=["address"]).any(), "Duplicate addresses in canonical!"
    assert not graph_features_df.duplicated(subset=["address"]).any(), "Duplicate addresses in graph features!"
    
    df_with_graph = canonical.merge(graph_features_df, on="address", how="left")
    assert len(df_with_graph) == len(canonical), (
        f"Row count changed after graph merge: {len(canonical)} -> {len(df_with_graph)}"
    )
    
    # Fill NaN graph features only for wallets genuinely absent from the graph
    for col in GRAPH_FEATURE_COLUMNS:
        df_with_graph[col] = df_with_graph[col].fillna(0.0)
    
    # Split by time step
    df_with_graph["Time step"] = pd.to_numeric(df_with_graph["Time step"], errors="coerce")
    
    train_df = df_with_graph[df_with_graph["Time step"].le(29)].copy()
    val_df = df_with_graph[df_with_graph["Time step"].between(30, 34)].copy()
    test_df = df_with_graph[df_with_graph["Time step"].ge(35)].copy()
    
    logger.info(f"Training set: {len(train_df)} rows from time steps 1-29")
    logger.info(f"Validation set: {len(val_df)} rows from time steps 30-34")
    logger.info(f"Test set: {len(test_df)} rows from time steps 35-49")
    
    return train_df, val_df, test_df


def train_with_graph_features(data_dir: str | None = None) -> dict:
    """
    Train XGBoost with engineered graph features using EXACT production baseline hyperparameters.
    
    Hyperparameters (IDENTICAL to production):
      - n_estimators=150
      - scale_pos_weight=computed
      - max_depth=5, learning_rate=0.06, subsample=0.85, colsample_bytree=0.85
    
    Returns:
        dict with training metrics and validation results
    """
    data_dir = data_dir or get_data_dir()
    
    # Load data with graph features
    train_df, val_df, test_df = load_training_data_with_graph_features(data_dir)
    
    # Prepare feature matrix
    all_feature_cols = [c for c in FEATURE_COLUMNS if c not in ["address", "label"]]
    
    X_train = train_df[all_feature_cols].fillna(0.0)
    y_train = train_df["label"].astype(int)
    
    X_val = val_df[all_feature_cols].fillna(0.0)
    y_val = val_df["label"].astype(int)
    
    X_test = test_df[all_feature_cols].fillna(0.0)
    y_test = test_df["label"].astype(int)
    
    # Verify feature schema
    assert_feature_schema(all_feature_cols)
    
    logger.info(f"Training on {len(X_train)} samples with {len(all_feature_cols)} features")
    logger.info(f"Class balance in training: {y_train.sum()} illicit / {len(y_train) - y_train.sum()} licit")
    
    # Compute scale_pos_weight (EXACT same as baseline)
    scale_pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())
    logger.info(f"scale_pos_weight = {scale_pos_weight:.4f}")
    
    # Train with EXACT baseline hyperparameters
    clf = xgb.XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42,
        tree_method="hist",
    )
    
    logger.info("Training XGBoost...")
    clf.fit(X_train, y_train)
    
    # Threshold selection on validation set (SAME procedure as baseline)
    locked_threshold, val_summary = select_best_threshold(
        y_val, clf.predict_proba(X_val)[:, 1]
    )
    
    # Evaluate on test set
    y_pred_test = (clf.predict_proba(X_test)[:, 1] >= locked_threshold).astype(int)
    y_prob_test = clf.predict_proba(X_test)[:, 1]
    
    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    test_precision = tp / max(1, (tp + fp))
    test_recall = tp / max(1, (tp + fn))
    test_fpr = fp / max(1, (fp + tn))
    test_auc_pr = average_precision_score(y_test, y_prob_test)
    test_auc_roc = roc_auc_score(y_test, y_prob_test)
    
    logger.info(f"\n[TEST SET RESULTS (Time Steps 35-49)]")
    logger.info(f"Threshold: {locked_threshold:.2f}")
    logger.info(f"Precision: {test_precision:.4f}")
    logger.info(f"Recall: {test_recall:.4f}")
    logger.info(f"FPR: {test_fpr:.4f} ({test_fpr*100:.2f}%)")
    logger.info(f"AUC-PR: {test_auc_pr:.4f}")
    logger.info(f"AUC-ROC: {test_auc_roc:.4f}")
    
    # Compute SHAP importance for graph features
    logger.info("\nComputing SHAP importance for all features...")
    shap_sample = X_test.sample(n=min(2000, len(X_test)), random_state=42)
    shap_values = shap.TreeExplainer(clf).shap_values(shap_sample)
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    
    # Identify graph feature indices
    graph_feature_importance = {}
    for graph_col in GRAPH_FEATURE_COLUMNS:
        if graph_col in all_feature_cols:
            idx = all_feature_cols.index(graph_col)
            importance = float(np.abs(shap_values[:, idx]).mean())
            graph_feature_importance[graph_col] = importance
    
    logger.info("Graph feature SHAP importance:")
    for col, imp in sorted(graph_feature_importance.items(), key=lambda x: x[1], reverse=True):
        logger.info(f"  {col}: {imp:.6f}")
    
    # Save model
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    model_path_graph = os.path.join(ARTIFACTS_DIR, "risk_model_with_graph_features.joblib")
    joblib.dump(clf, model_path_graph)
    logger.info(f"Saved model to {model_path_graph}")
    
    # Save metrics report
    report = {
        "model": "xgboost_with_graph_features",
        "feature_count": len(all_feature_cols),
        "feature_schema": {
            "tabular_count": len([c for c in FEATURE_COLUMNS if c not in GRAPH_FEATURE_COLUMNS]),
            "graph_feature_count": len(GRAPH_FEATURE_COLUMNS),
            "graph_features": GRAPH_FEATURE_COLUMNS,
        },
        "hyperparameters": {
            "n_estimators": 150,
            "max_depth": 5,
            "learning_rate": 0.06,
            "subsample": 0.85,
            "colsample_bytree": 0.85,
            "scale_pos_weight": float(scale_pos_weight),
        },
        "locked_threshold": locked_threshold,
        "validation": val_summary,
        "test_metrics": {
            "precision": test_precision,
            "recall": test_recall,
            "fpr": test_fpr,
            "auc_pr": test_auc_pr,
            "auc_roc": test_auc_roc,
            "tp": int(tp),
            "fp": int(fp),
            "tn": int(tn),
            "fn": int(fn),
        },
        "graph_feature_shap_importance": graph_feature_importance,
    }
    
    metrics_path_graph = os.path.join(ARTIFACTS_DIR, "risk_model_metrics_with_graph_features.json")
    with open(metrics_path_graph, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    logger.info(f"Saved metrics to {metrics_path_graph}")
    
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    report = train_with_graph_features()
    print("\n" + "="*70)
    print("TRAINING WITH GRAPH FEATURES COMPLETE")
    print("="*70)
    print(json.dumps(report, indent=2))
