"""
app/ml/train.py — Train XGBoost model on Elliptic++ Actors Dataset with 3-way temporal split.

Partitions:
  - Train set: Time steps 1..29 (Model parameter fitting)
  - Validation slice: Time steps 30..34 (Threshold optimization without test leakage)
  - Test set: Time steps 35..49 (Single out-of-sample application at locked threshold)

Metrics reported in priority order (docs/ml.md):
  1. AUC-PR (primary)
  2. Precision & Recall at deployed threshold
  3. False-Positive Rate (FPR) at deployed threshold (target < 1%)
  4. AUC-ROC (secondary)
  5. Calibration / Brier score
"""
import argparse
import logging
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    auc,
    brier_score_loss,
    confusion_matrix,
    precision_recall_curve,
    roc_auc_score,
)
import xgboost as xgb

from app.ml.features import FEATURE_COLUMNS, assert_feature_schema

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "risk_model.joblib")


def generate_realistic_elliptic_dataset(n_samples: int = 25000, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Generate realistic tabular data matching the Elliptic++ 55-feature schema across 49 time steps.
    Incorporates realistic non-linear distributions, class overlap (licit high-volume traders,
    illicit micro-transactions), noise, and temporal drift.
    """
    rng = np.random.RandomState(seed)
    
    # 49 time steps
    time_steps = rng.randint(1, 50, size=n_samples)
    
    # Realistic base fraud rate in Bitcoin network (~6.5% illicit)
    is_illicit = (rng.rand(n_samples) < 0.065).astype(int)
    classes = np.where(is_illicit == 1, 1, 2)

    # Base latent factors with higher variance and overlapping support
    latent_activity = rng.gamma(shape=1.8, scale=2.5, size=n_samples)
    latent_volume = rng.lognormal(mean=0.8, sigma=1.5, size=n_samples)
    
    # Substantial class overlap between licit entities (whales/traders) and illicit entities (mixers/scammers)
    suspicion_signal = is_illicit * rng.beta(a=2.0, b=1.5, size=n_samples) + (1 - is_illicit) * rng.beta(a=1.0, b=2.2, size=n_samples)
    
    # Temporal drift: activity scales and shifts across time steps
    time_factor = 1.0 + (time_steps / 50.0) * 0.4

    data = {}
    for col in FEATURE_COLUMNS:
        noise = rng.normal(0, 0.8, size=n_samples)
        
        if "num_txs_as_sender" in col or "total_txs" in col:
            val = latent_activity * (1.0 + 1.8 * suspicion_signal) * time_factor + np.abs(noise) * 8.0
            data[col] = np.clip(np.round(val), 1.0, 500.0)
        elif "num_txs_as receiver" in col:
            val = latent_activity * (1.0 + 1.2 * (1 - suspicion_signal * 0.5)) * time_factor + np.abs(noise) * 5.0
            data[col] = np.clip(np.round(val), 0.0, 300.0)
        elif "btc_transacted_total" in col or "btc_sent_total" in col or "btc_received_total" in col:
            val = latent_volume * (0.8 + 1.4 * suspicion_signal) * time_factor + np.abs(noise) * 2.0
            data[col] = np.clip(np.round(val, 4), 0.001, 1000.0)
        elif "btc_" in col and ("min" in col or "max" in col or "mean" in col or "median" in col):
            val = (latent_volume / (latent_activity + 1.0)) * (0.6 + 1.0 * suspicion_signal) + np.abs(noise) * 0.5
            data[col] = np.clip(np.round(val, 4), 0.0001, 500.0)
        elif "fees" in col:
            val = (latent_volume * 0.0001) * (1.0 + suspicion_signal * 0.8) + np.abs(noise) * 0.0001
            data[col] = np.clip(np.round(val, 6), 0.00001, 0.05)
        elif "lifetime" in col or "blocks_btwn" in col:
            base_life = rng.exponential(scale=2500.0, size=n_samples)
            life_mod = np.where(is_illicit == 1, base_life * 0.6 + rng.uniform(100, 2000, n_samples), base_life + rng.uniform(200, 4000, n_samples))
            data[col] = np.clip(np.round(life_mod), 0.0, 50000.0)
        elif "num_addr_transacted_multiple" in col or "transacted_w_address" in col:
            val = np.clip(np.round(latent_activity * (0.8 + 1.2 * suspicion_signal) + np.abs(noise) * 3.0), 1.0, 100.0)
            data[col] = val
        elif "first_block" in col or "last_block" in col:
            base_block = 400000 + time_steps * 1500 + rng.randint(-100, 100, size=n_samples)
            data[col] = base_block.astype(float)
        elif "first_sent" in col or "first_received" in col:
            base_block = 400000 + time_steps * 1500 + rng.randint(-100, 100, size=n_samples)
            data[col] = base_block.astype(float)
        elif "num_timesteps_appeared_in" in col:
            data[col] = np.clip(np.round(1.0 + rng.poisson(lam=1.5, size=n_samples)), 1.0, 10.0)
        else:
            data[col] = np.clip(rng.uniform(0.0, 10.0, size=n_samples) + suspicion_signal * 3.0 + noise, 0.0, 50.0)

    df_features = pd.DataFrame(data)
    df_features["Time step"] = time_steps
    # Unique addresses to guarantee zero overlap across samples
    df_features["address"] = [f"1Addr{i:08x}" for i in range(n_samples)]

    df_classes = pd.DataFrame({
        "address": df_features["address"],
        "class": classes,
    })

    return df_features, df_classes


def select_best_threshold(
    y_val: pd.Series,
    y_prob_val: np.ndarray,
    candidate_thresholds: list[float] = [0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85],
    max_fpr: float = 0.010,
) -> tuple[float, dict]:
    """
    Select optimal classification threshold on VALIDATION SLICE ONLY.
    Finds threshold that maximizes Recall subject to FPR < max_fpr (1.0%).
    """
    print("\n[THRESHOLD SCAN ON VALIDATION SLICE (Time Steps 30..34)]")
    print(f"{'Threshold':>10} | {'Precision':>10} | {'Recall':>10} | {'FPR':>10} | {'FPR < 1%':>8}")
    print("-" * 58)

    best_thresh = None
    best_recall = -1.0
    best_val_metrics = {}

    for t in candidate_thresholds:
        y_pred = (y_prob_val >= t).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_val, y_pred).ravel()
        prec = tp / max(1, (tp + fp))
        rec = tp / max(1, (tp + fn))
        fpr = fp / max(1, (fp + tn))
        meets_req = fpr <= max_fpr

        print(f"{t:>10.2f} | {prec:>10.4f} | {rec:>10.4f} | {fpr:>9.4f} ({fpr*100:.2f}%) | {'YES' if meets_req else 'NO':>8}")

        if meets_req and rec > best_recall:
            best_recall = rec
            best_thresh = t
            best_val_metrics = {
                "threshold": t,
                "precision": prec,
                "recall": rec,
                "fpr": fpr,
                "tp": int(tp),
                "fp": int(fp),
                "tn": int(tn),
                "fn": int(fn),
            }

    # Fallback if none strictly meets max_fpr (take highest threshold)
    if best_thresh is None:
        best_thresh = max(candidate_thresholds)

    print("-" * 58)
    print(f"Locked Threshold from Validation: {best_thresh:.2f} (Val Recall: {best_val_metrics.get('recall', 0):.4f}, Val FPR: {best_val_metrics.get('fpr', 0)*100:.2f}%)\n")

    return best_thresh, best_val_metrics


def train_elliptic_model(
    df_features: pd.DataFrame,
    df_classes: pd.DataFrame,
) -> dict:
    """
    Train XGBoost on temporal split with separate validation slice for threshold tuning.
      1. Train: Time steps 1..29
      2. Validation: Time steps 30..34 (Threshold optimization)
      3. Test: Time steps 35..49 (Untouched holdout evaluation)
    """
    # ── Deduplicate rows after join ───────────────────────────────────────────
    df = pd.merge(df_features, df_classes, on="address")
    initial_len = len(df)
    df = df.drop_duplicates(subset=["address"], keep="last").copy()
    print(f"Deduplication on address: {initial_len} -> {len(df)} rows.")

    # Filter out unknown class (class 3) if present
    df = df[df["class"].isin([1, 2])].copy()
    df["label"] = (df["class"] == 1).astype(int)

    # ── 3-Way Temporal Partitioning ───────────────────────────────────────────
    train_mask = df["Time step"] <= 29
    val_mask = (df["Time step"] >= 30) & (df["Time step"] <= 34)
    test_mask = df["Time step"] >= 35

    train_df = df[train_mask]
    val_df = df[val_mask]
    test_df = df[test_mask]

    train_addrs = set(train_df["address"].tolist())
    val_addrs = set(val_df["address"].tolist())
    test_addrs = set(test_df["address"].tolist())

    # Assert 0 address overlap across all 3 sets
    assert len(train_addrs.intersection(val_addrs)) == 0, "Overlap between Train and Val!"
    assert len(train_addrs.intersection(test_addrs)) == 0, "Overlap between Train and Test!"
    assert len(val_addrs.intersection(test_addrs)) == 0, "Overlap between Val and Test!"

    print(f"Temporal Split Audit:")
    print(f"  Train: steps 1..29  (N={len(train_df)}, Illicit={train_df['label'].sum()}, BaseRate={train_df['label'].mean():.2%})")
    print(f"  Val:   steps 30..34 (N={len(val_df)}, Illicit={val_df['label'].sum()}, BaseRate={val_df['label'].mean():.2%})")
    print(f"  Test:  steps 35..49 (N={len(test_df)}, Illicit={test_df['label'].sum()}, BaseRate={test_df['label'].mean():.2%})")

    # Assert feature schema (55 features, no target or ID leakage)
    assert_feature_schema(FEATURE_COLUMNS)

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df["label"]

    X_val = val_df[FEATURE_COLUMNS]
    y_val = val_df["label"]

    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df["label"]

    # ── Model Training on Train set ONLY (Time steps 1..29) ───────────────────
    scale_pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())
    clf = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=4,
        learning_rate=0.06,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=scale_pos_weight,
        eval_metric="logloss",
        random_state=42,
    )
    clf.fit(X_train, y_train)

    # ── Threshold Selection on Validation Slice ONLY (Time steps 30..34) ──────
    y_prob_val = clf.predict_proba(X_val)[:, 1]
    locked_threshold, val_metrics = select_best_threshold(y_val, y_prob_val)

    # Compute validation AUC-PR and AUC-ROC
    val_prec_curve, val_rec_curve, _ = precision_recall_curve(y_val, y_prob_val)
    val_auc_pr = auc(val_rec_curve, val_prec_curve)
    val_auc_roc = roc_auc_score(y_val, y_prob_val)
    val_brier = brier_score_loss(y_val, y_prob_val)

    # ── Single Evaluation on UNTOUCHED Test Set (Time steps 35..49) ───────────
    y_prob_test = clf.predict_proba(X_test)[:, 1]
    y_pred_test = (y_prob_test >= locked_threshold).astype(int)

    test_prec_curve, test_rec_curve, _ = precision_recall_curve(y_test, y_prob_test)
    test_auc_pr = auc(test_rec_curve, test_prec_curve)
    test_auc_roc = roc_auc_score(y_test, y_prob_test)
    test_brier = brier_score_loss(y_test, y_prob_test)

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    test_precision = tp / max(1, (tp + fp))
    test_recall = tp / max(1, (tp + fn))
    test_fpr = fp / max(1, (fp + tn))

    test_metrics = {
        "locked_threshold": locked_threshold,
        "auc_pr": round(float(test_auc_pr), 4),
        "precision_at_threshold": round(float(test_precision), 4),
        "recall_at_threshold": round(float(test_recall), 4),
        "fpr_at_threshold": round(float(test_fpr), 4),
        "auc_roc": round(float(test_auc_roc), 4),
        "brier_score": round(float(test_brier), 4),
        "test_tp": int(tp),
        "test_fp": int(fp),
        "test_tn": int(tn),
        "test_fn": int(fn),
    }

    # ── Report Both Metrics Side by Side ──────────────────────────────────────
    print("=======================================================================")
    print(f"  VALIDATION SLICE (Steps 30..34) vs. UNTOUCHED TEST SET (Steps 35..49)")
    print(f"  Locked Threshold: {locked_threshold:.2f}")
    print("=======================================================================")
    print(f"{'Metric':<32} | {'Val Slice (Steps 30..34)':<22} | {'Test Set (Steps 35..49)':<22}")
    print("-" * 80)
    print(f"{'1. AUC-PR (Primary Metric)':<32} | {val_auc_pr:<22.4f} | {test_auc_pr:<22.4f}")
    print(f"{'2. Precision at Threshold':<32} | {val_metrics['precision']:<22.4f} | {test_precision:<22.4f}")
    print(f"{'   Recall at Threshold':<32} | {val_metrics['recall']:<22.4f} | {test_recall:<22.4f}")
    print(f"{'3. False-Positive Rate (FPR < 1%)':<32} | {val_metrics['fpr']*100:<21.2f}% | {test_fpr*100:<21.2f}%")
    print(f"{'4. AUC-ROC (Secondary Metric)':<32} | {val_auc_roc:<22.4f} | {test_auc_roc:<22.4f}")
    print(f"{'5. Brier Calibration Score':<32} | {val_brier:<22.4f} | {test_brier:<22.4f}")
    print("-" * 80)
    print(f"Test Confusion Matrix: TP={tp}, FP={fp}, TN={tn}, FN={fn} (Total={len(test_df)})")
    print("=======================================================================\n")

    # Save trained model artifact
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    print(f"Model successfully saved to {MODEL_PATH}")

    return {
        "val_metrics": {
            "threshold": locked_threshold,
            "auc_pr": round(float(val_auc_pr), 4),
            "precision": round(float(val_metrics["precision"]), 4),
            "recall": round(float(val_metrics["recall"]), 4),
            "fpr": round(float(val_metrics["fpr"]), 4),
            "auc_roc": round(float(val_auc_roc), 4),
            "brier": round(float(val_brier), 4),
        },
        "test_metrics": test_metrics,
    }


def main():
    parser = argparse.ArgumentParser(description="Train Elliptic++ Risk Model with 3-way temporal split")
    parser.add_argument("--samples", type=int, default=25000, help="Number of synthetic sample rows")
    args = parser.parse_args()

    df_features, df_classes = generate_realistic_elliptic_dataset(n_samples=args.samples)
    train_elliptic_model(df_features, df_classes)


if __name__ == "__main__":
    main()
