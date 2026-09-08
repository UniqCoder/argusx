"""Non-production BTC drift, ablation, and probability calibration experiments."""
from __future__ import annotations

import json
import os
from typing import Iterable

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import auc, brier_score_loss, f1_score, precision_recall_curve, precision_score, recall_score, roc_auc_score

from app.ml.features import FEATURE_COLUMNS
from app.ml.model import MODEL_PATH
from app.ml.train import build_combined_training_dataframe, evaluate_chain_metrics, stratified_chain_split

REPORT_PATH = os.path.join(os.path.dirname(__file__), "artifacts", "risk_model_robustness_report.json")
LOCKED_THRESHOLD = 0.90
CANDIDATE_THRESHOLDS = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
ABLATION_FEATURES = [
    "first_sent_block",
    "lifetime_in_blocks",
    "first_block_appeared_in",
    "last_block_appeared_in",
]


def make_model() -> xgb.XGBClassifier:
    return xgb.XGBClassifier(
        n_estimators=150,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="logloss",
        random_state=42,
        tree_method="hist",
    )


def metrics(model: xgb.XGBClassifier, frame: pd.DataFrame, threshold: float = LOCKED_THRESHOLD) -> dict:
    probabilities = model.predict_proba(frame[FEATURE_COLUMNS].fillna(0.0))[:, 1]
    labels = frame["label"]
    predictions = (probabilities >= threshold).astype(int)
    precision, recall, _ = precision_recall_curve(labels, probabilities)
    return {
        "rows": int(len(frame)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "auc_pr": float(auc(recall, precision)),
        "brier": float(brier_score_loss(labels, probabilities)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
    }


def step_breakdown(model: xgb.XGBClassifier, frame: pd.DataFrame, threshold: float = LOCKED_THRESHOLD) -> dict:
    output = {}
    for step, step_frame in frame.groupby("time_step"):
        output[str(int(step))] = metrics(model, step_frame, threshold)
    return output


def train_btc(train: pd.DataFrame, feature_subset: Iterable[str] = FEATURE_COLUMNS, recency_weighted: bool = False) -> xgb.XGBClassifier:
    feature_subset = list(feature_subset)
    model = make_model()
    labels = train["label"]
    class_weight = (len(labels) - labels.sum()) / max(1, labels.sum())
    sample_weight = np.where(labels.to_numpy() == 1, class_weight, 1.0).astype(float)
    if recency_weighted:
        normalized_age = (train["time_step"].to_numpy() - 1.0) / 28.0
        sample_weight *= 1.0 + normalized_age
    model.fit(train[feature_subset].fillna(0.0), labels, sample_weight=sample_weight)
    return model


def metrics_subset(model: xgb.XGBClassifier, frame: pd.DataFrame, feature_subset: list[str]) -> dict:
    probabilities = model.predict_proba(frame[feature_subset].fillna(0.0))[:, 1]
    labels = frame["label"]
    predictions = (probabilities >= LOCKED_THRESHOLD).astype(int)
    precision, recall, _ = precision_recall_curve(labels, probabilities)
    return {
        "rows": int(len(frame)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1": float(f1_score(labels, predictions, zero_division=0)),
        "auc_pr": float(auc(recall, precision)),
    }


def threshold_scan(
    model: xgb.XGBClassifier,
    frame: pd.DataFrame,
    feature_subset: Iterable[str] = FEATURE_COLUMNS,
) -> tuple[float, list[dict]]:
    """Select a threshold using validation FPR <= 2%, never using test labels."""
    feature_subset = list(feature_subset)
    probabilities = model.predict_proba(frame[feature_subset].fillna(0.0))[:, 1]
    labels = frame["label"].to_numpy()
    scan = []
    for threshold in CANDIDATE_THRESHOLDS:
        predictions = probabilities >= threshold
        negatives = labels == 0
        positives = labels == 1
        fp = int((predictions & negatives).sum())
        tn = int((~predictions & negatives).sum())
        tp = int((predictions & positives).sum())
        fn = int((~predictions & positives).sum())
        fpr = fp / max(1, fp + tn)
        recall = tp / max(1, tp + fn)
        scan.append({"threshold": threshold, "fpr": fpr, "recall": recall, "precision": tp / max(1, tp + fp)})
    eligible = [row for row in scan if row["fpr"] <= 0.02]
    locked = max(eligible, key=lambda row: row["recall"])["threshold"] if eligible else max(CANDIDATE_THRESHOLDS)
    return locked, scan


def run() -> dict:
    combined = build_combined_training_dataframe()
    btc = combined[combined["chain"] == "BTC"]
    eth_train, eth_val, eth_test = stratified_chain_split(combined[combined["chain"] == "ETH"])
    btc_train = btc[btc["time_step"] <= 29]
    btc_val = btc[btc["time_step"].between(30, 34)]
    btc_test = btc[btc["time_step"] >= 35]

    baseline_model = joblib.load(MODEL_PATH)
    baseline_btc = metrics(baseline_model, btc_test)
    baseline_btc["per_time_step"] = step_breakdown(baseline_model, btc_test)
    baseline_eth = metrics(baseline_model, eth_test)

    drift_model = train_btc(btc_train, recency_weighted=True)
    recency_threshold, recency_threshold_scan = threshold_scan(drift_model, btc_val)
    drift_btc = metrics(drift_model, btc_test, recency_threshold)
    drift_btc["per_time_step"] = step_breakdown(drift_model, btc_test, recency_threshold)

    combined_subset = [column for column in FEATURE_COLUMNS if column != "last_block_appeared_in"]
    combined_model = train_btc(btc_train, combined_subset, recency_weighted=True)
    combined_threshold, combined_threshold_scan = threshold_scan(combined_model, btc_val, combined_subset)
    combined_btc = metrics_subset(combined_model, btc_test, combined_subset)
    combined_btc["locked_threshold"] = combined_threshold
    combined_btc["threshold_scan_validation"] = combined_threshold_scan
    combined_btc["per_time_step"] = {}
    for step, step_frame in btc_test.groupby("time_step"):
        combined_btc["per_time_step"][str(int(step))] = metrics_subset(combined_model, step_frame, combined_subset)

    ablation_validation = {}
    ablation_models = {}
    for feature in ABLATION_FEATURES:
        subset = [column for column in FEATURE_COLUMNS if column != feature]
        model = train_btc(btc_train, subset)
        ablation_models[feature] = (model, subset)
        ablation_validation[feature] = metrics_subset(model, btc_val, subset)
    combined_subset = [column for column in FEATURE_COLUMNS if column not in ABLATION_FEATURES]
    combined_model = train_btc(btc_train, combined_subset)
    ablation_models["combined"] = (combined_model, combined_subset)
    ablation_validation["combined"] = metrics_subset(combined_model, btc_val, combined_subset)
    selected_ablation = max(
        ablation_validation,
        key=lambda name: (ablation_validation[name]["f1"], ablation_validation[name]["auc_pr"]),
    )
    selected_model, selected_subset = ablation_models[selected_ablation]
    selected_ablation_test = metrics_subset(selected_model, btc_test, selected_subset)

    calibration = {}
    for chain, validation, test in (("BTC", btc_val, btc_test), ("ETH", eth_val, eth_test)):
        raw_validation = baseline_model.predict_proba(validation[FEATURE_COLUMNS].fillna(0.0))[:, 1]
        raw_test = baseline_model.predict_proba(test[FEATURE_COLUMNS].fillna(0.0))[:, 1]
        calibrator = LogisticRegression(solver="lbfgs", random_state=42)
        calibrator.fit(raw_validation.reshape(-1, 1), validation["label"])
        calibrated_test = calibrator.predict_proba(raw_test.reshape(-1, 1))[:, 1]
        calibration[chain] = {
            "validation_rows": int(len(validation)),
            "test_rows": int(len(test)),
            "raw_brier": float(brier_score_loss(test["label"], raw_test)),
            "platt_brier": float(brier_score_loss(test["label"], calibrated_test)),
            "raw_mean_probability": float(raw_test.mean()),
            "platt_mean_probability": float(calibrated_test.mean()),
        }

    report = {
        "threshold": LOCKED_THRESHOLD,
        "baseline": {"BTC": baseline_btc, "ETH": baseline_eth},
        "recency_weighted_btc": {
            "locked_threshold": recency_threshold,
            "threshold_scan_validation": recency_threshold_scan,
            "metrics": drift_btc,
        },
        "recency_plus_last_block_ablation_btc": combined_btc,
        "ablation_btc": {
            "selection_metric": "validation F1, then validation AUC-PR",
            "validation_candidates": ablation_validation,
            "selected_variant": selected_ablation,
            "selected_test_metrics": selected_ablation_test,
        },
        "platt_calibration": calibration,
        "notes": {
            "production_artifact_replaced": False,
            "recency_weight": "class-balanced weight multiplied by (1 + (time_step - 1) / 28)",
            "eth_split": "class-stratified 70/15/15",
            "btc_test_steps": "35-49",
        },
    }
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=2)
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    run()
