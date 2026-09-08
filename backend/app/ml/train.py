"""
app/ml/train.py — Train XGBoost model on REAL Elliptic++ Actors Dataset with 3-way temporal split.

Dataset Location:
  - data/raw/ellipticpp/wallets_features.csv
  - data/raw/ellipticpp/wallets_classes.csv

Partitions (Time steps 1..49):
  - Train set: Time steps 1..29 (Model parameter fitting on historical graph)
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
import json
import logging
import os
import time
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import (
    auc,
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    precision_recall_curve,
    recall_score,
    roc_auc_score,
)
import xgboost as xgb
import shap

from app.ml.embedding_store import lookup_embedding
from app.ml.features import FEATURE_COLUMNS, GSAGE_EMBEDDING_COLUMNS, MISSING_INDICATOR_COLUMNS, MODEL_FEATURE_COLUMNS, assert_feature_schema, assert_model_feature_schema
from app.ml.relative_features import REFERENCE_PATH, RELATIVE_FEATURE_COLUMNS, apply_relative_features, fit_relative_reference, load_relative_reference, save_relative_reference
from app.ml.snapshot_graph_features import GRAPH_FEATURE_COLS

logger = logging.getLogger(__name__)

# Search paths for raw Elliptic++ CSV dataset files
POSSIBLE_DATA_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "ellipticpp")),
    "/app/data/raw/ellipticpp",
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "raw", "ellipticpp")),
    os.path.abspath(os.path.join(os.getcwd(), "data", "raw", "ellipticpp")),
]
ETHEREUM_DATA_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "backend", "data", "raw", "ethereum_fraud")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "raw", "ethereum_fraud")),
    "/app/data/raw/ethereum_fraud",
]

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "risk_model.joblib")
METRICS_PATH = os.path.join(ARTIFACTS_DIR, "risk_model_metrics.json")

DATASET_TO_CANONICAL_RENAME: dict[str, str] = {
    "num_txs_as_sender": "num_txs_as_sender",
    "num_txs_as receiver": "num_txs_as_receiver",
    "first_block_appeared_in": "first_block_appeared_in",
    "last_block_appeared_in": "last_block_appeared_in",
    "lifetime_in_blocks": "lifetime_in_blocks",
    "total_txs": "total_txs",
    "first_sent_block": "first_sent_block",
    "first_received_block": "first_received_block",
    "num_timesteps_appeared_in": "num_timesteps_appeared_in",
    "btc_transacted_total": "value_transacted_total",
    "btc_transacted_min": "value_transacted_min",
    "btc_transacted_max": "value_transacted_max",
    "btc_transacted_mean": "value_transacted_mean",
    "btc_transacted_median": "value_transacted_median",
    "btc_sent_total": "value_sent_total",
    "btc_sent_min": "value_sent_min",
    "btc_sent_max": "value_sent_max",
    "btc_sent_mean": "value_sent_mean",
    "btc_sent_median": "value_sent_median",
    "btc_received_total": "value_received_total",
    "btc_received_min": "value_received_min",
    "btc_received_max": "value_received_max",
    "btc_received_mean": "value_received_mean",
    "btc_received_median": "value_received_median",
    "fees_total": "chain_fee_total",
    "fees_min": "chain_fee_min",
    "fees_max": "chain_fee_max",
    "fees_mean": "chain_fee_mean",
    "fees_median": "chain_fee_median",
    "fees_as_share_total": "fee_ratio_total",
    "fees_as_share_min": "fee_ratio_min",
    "fees_as_share_max": "fee_ratio_max",
    "fees_as_share_mean": "fee_ratio_mean",
    "fees_as_share_median": "fee_ratio_median",
    "blocks_btwn_txs_total": "time_between_txs_total",
    "blocks_btwn_txs_min": "time_between_txs_min",
    "blocks_btwn_txs_max": "time_between_txs_max",
    "blocks_btwn_txs_mean": "time_between_txs_mean",
    "blocks_btwn_txs_median": "time_between_txs_median",
    "blocks_btwn_input_txs_total": "time_between_input_txs_total",
    "blocks_btwn_input_txs_min": "time_between_input_txs_min",
    "blocks_btwn_input_txs_max": "time_between_input_txs_max",
    "blocks_btwn_input_txs_mean": "time_between_input_txs_mean",
    "blocks_btwn_input_txs_median": "time_between_input_txs_median",
    "blocks_btwn_output_txs_total": "time_between_output_txs_total",
    "blocks_btwn_output_txs_min": "time_between_output_txs_min",
    "blocks_btwn_output_txs_max": "time_between_output_txs_max",
    "blocks_btwn_output_txs_mean": "time_between_output_txs_mean",
    "blocks_btwn_output_txs_median": "time_between_output_txs_median",
    "num_addr_transacted_multiple": "num_addr_transacted_multiple",
    "transacted_w_address_total": "transacted_w_address_total",
    "transacted_w_address_min": "transacted_w_address_min",
    "transacted_w_address_max": "transacted_w_address_max",
    "transacted_w_address_mean": "transacted_w_address_mean",
    "transacted_w_address_median": "transacted_w_address_median",
}
DATASET_FEATURE_COLUMNS = list(DATASET_TO_CANONICAL_RENAME.keys())


def canonicalize_training_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Map historical Elliptic++ names into the canonical inference schema."""
    canonical = frame.rename(columns=DATASET_TO_CANONICAL_RENAME)
    missing = [column for column in FEATURE_COLUMNS if column not in canonical.columns]
    if missing:
        canonical = canonical.assign(**{column: np.nan for column in missing})
    canonical = add_missing_indicators(canonical)
    assert_feature_schema([column for column in FEATURE_COLUMNS if column in canonical.columns])
    return canonical[FEATURE_COLUMNS]


def add_missing_indicators(frame: pd.DataFrame) -> pd.DataFrame:
    """Encode structural missingness before numeric imputation."""
    indicator_sources = {
        "chain_fee_is_missing": "chain_fee_total",
        "fee_ratio_is_missing": "fee_ratio_total",
        "native_fee_is_missing": "native_fee_units_total",
        "gas_price_is_missing": "gas_price_gwei_mean",
        "gas_used_is_missing": "gas_used_mean",
        "bandwidth_is_missing": "bandwidth_used_total",
        "energy_is_missing": "energy_used_total",
    }
    for indicator, source in indicator_sources.items():
        frame[indicator] = frame[source].isna().astype(float)
    return frame


def evaluate_model(
    clf: xgb.XGBClassifier,
    X: pd.DataFrame,
    y: pd.Series,
    threshold: float,
    split_name: str,
) -> dict:
    """Evaluate a trained model and measure single-row inference performance."""
    probabilities = clf.predict_proba(X)[:, 1]
    predictions = (probabilities >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, predictions, labels=[0, 1]).ravel()

    # Measure the deployed single-wallet inference path, excluding model warm-up.
    benchmark_X = X.iloc[: min(len(X), 2_000)]
    sample = benchmark_X.iloc[[0]]
    clf.predict_proba(sample)
    latency_samples_ms: list[float] = []
    started = time.perf_counter()
    for index in range(len(benchmark_X)):
        sample_started = time.perf_counter_ns()
        clf.predict_proba(benchmark_X.iloc[[index]])
        latency_samples_ms.append((time.perf_counter_ns() - sample_started) / 1_000_000)
    elapsed_seconds = time.perf_counter() - started

    metrics = {
        "split": split_name,
        "samples": int(len(y)),
        "inference_benchmark_samples": int(len(benchmark_X)),
        "threshold": float(threshold),
        "accuracy": float(accuracy_score(y, predictions)),
        "precision": float(precision_score(y, predictions, zero_division=0)),
        "recall": float(recall_score(y, predictions, zero_division=0)),
        "f1_score": float(f1_score(y, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, probabilities)),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
        "inference_latency_ms": {
            "p50": float(np.percentile(latency_samples_ms, 50)),
            "p95": float(np.percentile(latency_samples_ms, 95)),
        },
        "throughput_samples_per_second": float(len(benchmark_X) / max(elapsed_seconds, 1e-9)),
    }

    print(f"\n[{split_name.upper()} MODEL METRICS]")
    print(json.dumps(metrics, indent=2))
    return metrics


def get_data_dir() -> str:
    """Find valid directory containing real Elliptic++ CSV dataset files."""
    for d in POSSIBLE_DATA_DIRS:
        feat_path = os.path.join(d, "wallets_features.csv")
        class_path = os.path.join(d, "wallets_classes.csv")
        if os.path.exists(feat_path) and os.path.exists(class_path):
            return d
    raise FileNotFoundError(
        f"Real Elliptic++ dataset files (wallets_features.csv, wallets_classes.csv) not found!\n"
        f"Searched paths: {POSSIBLE_DATA_DIRS}\n"
        f"Please ensure real files are staged in data/raw/ellipticpp/."
    )


def load_real_elliptic_dataset(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load the real raw Elliptic++ Actors dataset CSV files from disk.
    No synthetic generation fallback allowed.
    """
    feat_path = os.path.join(data_dir, "wallets_features.csv")
    class_path = os.path.join(data_dir, "wallets_classes.csv")

    print(f"Loading real Elliptic++ features from {feat_path}...")
    df_features = pd.read_csv(feat_path)
    print(f"Loaded features: {df_features.shape[0]:,} rows, {df_features.shape[1]} columns.")

    print(f"Loading real Elliptic++ classes from {class_path}...")
    df_classes = pd.read_csv(class_path)
    print(f"Loaded classes: {df_classes.shape[0]:,} rows.")

    df_features["chain"] = "BTC"
    df_classes["chain"] = "BTC"

    return df_features, df_classes


def get_ethereum_fraud_path() -> str:
    """Find the staged Kaggle Ethereum wallet CSV."""
    for data_dir in ETHEREUM_DATA_DIRS:
        path = os.path.join(data_dir, "transaction_dataset.csv")
        if os.path.exists(path):
            return path
    raise FileNotFoundError(
        "Ethereum Fraud Detection CSV not found. Expected transaction_dataset.csv in "
        f"one of: {ETHEREUM_DATA_DIRS}"
    )


PROCESSED_DATA_DIRS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "processed")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "processed")),
    os.path.abspath(os.path.join(os.getcwd(), "data", "processed")),
]


def get_processed_dir() -> str:
    """Find preprocessed train/val/test CSVs at data/processed/."""
    for d in PROCESSED_DATA_DIRS:
        if os.path.exists(os.path.join(d, "train.csv")):
            return d
    raise FileNotFoundError(
        "Preprocessed data not found. Run preprocess.py first.\n"
        f"Searched paths: {PROCESSED_DATA_DIRS}"
    )


def load_ethereum_fraud_dataset(csv_path: str | None = None) -> pd.DataFrame:
    """Load and map the Kaggle Ethereum wallet labels into canonical features."""
    path = csv_path or get_ethereum_fraud_path()
    source = pd.read_csv(path)
    source.columns = [str(column).strip() for column in source.columns]
    print(f"Loaded Ethereum fraud dataset: {len(source):,} rows, {len(source.columns):,} columns.")
    print(f"Ethereum class balance: non-fraud={int((source['FLAG'] == 0).sum()):,} ({(source['FLAG'] == 0).mean():.4%}), "
          f"fraud={int((source['FLAG'] == 1).sum()):,} ({(source['FLAG'] == 1).mean():.4%})")
    print("Ethereum source columns:")
    print("\n".join(f"  {index}. {column}" for index, column in enumerate(source.columns, start=1)))

    def numeric(name: str) -> pd.Series:
        return pd.to_numeric(source.get(name, pd.Series(np.nan, index=source.index)), errors="coerce")

    canonical = pd.DataFrame(np.nan, index=source.index, columns=FEATURE_COLUMNS)
    direct_map = {
        "num_txs_as_sender": "Sent tnx",
        "num_txs_as_receiver": "Received Tnx",
        "lifetime_in_blocks": "Time Diff between first and last (Mins)",
        "total_txs": "total transactions (including tnx to create contract",
        "value_received_min": "min value received",
        "value_received_max": "max value received",
        "value_received_mean": "avg val received",
        "value_sent_min": "min val sent",
        "value_sent_max": "max val sent",
        "value_sent_mean": "avg val sent",
        "value_transacted_total": "total Ether sent",
        "value_received_total": "total ether received",
        "value_sent_total": "total Ether sent",
        "transacted_w_address_total": "Unique Received From Addresses",
        "time_between_input_txs_mean": "Avg min between sent tnx",
        "time_between_output_txs_mean": "Avg min between received tnx",
        "value_transacted_mean": "avg val received",
    }
    derived_features = {
        "lifetime_in_blocks": "Time Diff between first and last (Mins), retained as a duration proxy",
        "value_transacted_min": "minimum of received and sent value minima",
        "value_transacted_max": "maximum of received and sent value maxima",
        "num_addr_transacted_multiple": "sum of unique received/sent counterparties as a conservative proxy",
        "time_between_txs_total": "Time Diff between first and last (Mins)",
        "time_between_txs_mean": "duration divided by total transaction count",
    }
    unavailable_features = [
        "first_block_appeared_in", "last_block_appeared_in", "first_sent_block", "first_received_block",
        "chain_fee_total", "chain_fee_min", "chain_fee_max", "chain_fee_mean", "chain_fee_median",
        "fee_ratio_total", "fee_ratio_min", "fee_ratio_max", "fee_ratio_mean", "fee_ratio_median",
        "native_fee_rate_mean", "native_fee_units_total", "native_fee_units_mean", "gas_price_gwei_mean",
        "gas_used_mean", "bandwidth_used_total", "energy_used_total",
        "time_between_txs_min", "time_between_txs_max", "time_between_txs_median",
        "time_between_input_txs_total", "time_between_input_txs_min", "time_between_input_txs_max",
        "time_between_input_txs_median", "time_between_output_txs_total", "time_between_output_txs_min",
        "time_between_output_txs_max", "time_between_output_txs_median",
        "transacted_w_address_min", "transacted_w_address_max", "transacted_w_address_mean",
        "transacted_w_address_median",
    ]
    print("Ethereum canonical mapping:")
    print("  Direct:", ", ".join(f"{target} <- {source_name}" for target, source_name in direct_map.items()))
    print("  Derived:", ", ".join(f"{target} <- {description}" for target, description in derived_features.items()))
    print("  Unavailable/null-imputed:", ", ".join(unavailable_features))
    for target, source_name in direct_map.items():
        canonical[target] = numeric(source_name)

    # These are valid Ethereum-derived equivalents; block heights, UTXO fees,
    # and transaction-level gas values are absent from this wallet aggregate.
    canonical["num_addr_transacted_multiple"] = (
        numeric("Unique Received From Addresses") + numeric("Unique Sent To Addresses")
    ).clip(lower=0)
    canonical["value_transacted_min"] = pd.concat(
        [numeric("min value received"), numeric("min val sent")], axis=1
    ).min(axis=1)
    canonical["value_transacted_max"] = pd.concat(
        [numeric("max value received"), numeric("max val sent")], axis=1
    ).max(axis=1)
    canonical["num_timesteps_appeared_in"] = 1.0
    # The source has contract-transfer totals, not transaction gas fees; do not
    # mislabel those values as chain fees.
    canonical["time_between_txs_mean"] = numeric("Time Diff between first and last (Mins)") / canonical["total_txs"].replace(0, np.nan)
    canonical["time_between_txs_total"] = numeric("Time Diff between first and last (Mins)")
    canonical["gas_price_gwei_mean"] = np.nan
    canonical["gas_used_mean"] = np.nan
    canonical["native_fee_rate_mean"] = np.nan
    canonical["native_fee_units_total"] = np.nan
    canonical["native_fee_units_mean"] = np.nan
    canonical["bandwidth_used_total"] = np.nan
    canonical["energy_used_total"] = np.nan
    canonical = add_missing_indicators(canonical)

    canonical["address"] = source["Address"].astype(str).str.lower()
    canonical["label"] = (numeric("FLAG") == 1).astype(int)
    canonical["chain"] = "ETH"
    return canonical


def build_combined_training_dataframe() -> pd.DataFrame:
    """Build labeled BTC + ETH rows with chain retained for separate evaluation."""
    btc_features, btc_classes = load_real_elliptic_dataset(get_data_dir())
    btc_labeled = pd.merge(btc_features, btc_classes[["address", "class"]], on="address")
    btc_labeled = btc_labeled.drop_duplicates()  # remove exact-copy rows first
    btc_labeled = btc_labeled.drop_duplicates(subset=["address"], keep="last")
    btc_labeled = btc_labeled[btc_labeled["class"].isin([1, 2])].copy()
    btc = canonicalize_training_features(btc_labeled)
    btc["address"] = btc_labeled["address"].astype(str).str.lower().to_numpy()
    btc["label"] = (btc_labeled["class"].to_numpy() == 1).astype(int)
    btc["chain"] = "BTC"
    btc["time_step"] = btc_labeled["Time step"].to_numpy()

    eth = load_ethereum_fraud_dataset()
    eth["time_step"] = np.nan
    combined = pd.concat([btc, eth], ignore_index=True, sort=False)
    combined = combined[combined["label"].isin([0, 1])].copy()
    print(f"Combined training dataframe shape: {combined.shape}")
    print("Rows per chain:")
    print(combined.groupby("chain").size().to_string())
    print("Class balance per chain:")
    print(combined.groupby("chain")["label"].agg(
        rows="size", fraud="sum", fraud_percent="mean"
    ).assign(fraud_percent=lambda frame: frame["fraud_percent"] * 100).to_string())
    return combined


def build_per_chain_sample_weights(train_df: pd.DataFrame) -> np.ndarray:
    """Balance fraud classes within each chain while giving chains equal mass."""
    weights = np.zeros(len(train_df), dtype=np.float64)
    for chain, indexes in train_df.groupby("chain").groups.items():
        labels = train_df.loc[indexes, "label"]
        positives = max(1, int(labels.sum()))
        negatives = max(1, int((labels == 0).sum()))
        class_weights = np.where(labels.to_numpy() == 1, negatives / positives, 1.0)
        weights[np.asarray(list(indexes))] = class_weights
    for chain, indexes in train_df.groupby("chain").groups.items():
        chain_indexes = np.asarray(list(indexes))
        weights[chain_indexes] *= 1.0 / max(weights[chain_indexes].sum(), 1.0)
    return weights * len(train_df) / max(weights.sum(), 1.0)


def evaluate_chain_metrics(
    clf: xgb.XGBClassifier,
    frame: pd.DataFrame,
    threshold: float,
    feature_columns: list[str] | None = None,
) -> dict:
    """Report threshold metrics and AUC-PR for one held-out chain."""
    columns = feature_columns or FEATURE_COLUMNS
    probabilities = clf.predict_proba(frame[columns].fillna(0.0))[:, 1]
    labels = frame["label"]
    predictions = (probabilities >= threshold).astype(int)
    precision, recall, _ = precision_recall_curve(labels, probabilities)
    return {
        "rows": int(len(frame)),
        "precision": float(precision_score(labels, predictions, zero_division=0)),
        "recall": float(recall_score(labels, predictions, zero_division=0)),
        "f1_score": float(f1_score(labels, predictions, zero_division=0)),
        "auc_pr": float(auc(recall, precision)),
        "roc_auc": float(roc_auc_score(labels, probabilities)),
    }


def stratified_chain_split(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split a chain's labeled rows 70/15/15 while preserving class balance."""
    partitions = [[], [], []]
    for _, class_frame in frame.groupby("label"):
        shuffled = class_frame.sample(frac=1.0, random_state=42)
        first = int(len(shuffled) * 0.70)
        second = first + int(len(shuffled) * 0.15)
        for slot, partition in enumerate((shuffled.iloc[:first], shuffled.iloc[first:second], shuffled.iloc[second:])):
            partitions[slot].append(partition)
    return tuple(pd.concat(partition, ignore_index=True) for partition in partitions)


def augment_frame_with_embeddings(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach the 16 GraphSAGE embedding columns (gsage_0..15) to a processed split frame.

    BTC rows whose address exists in the wallet embedding store get their real 16-dim
    embedding; every other row (ETH, non-graph BTC) gets a 16-dim zero vector, matching
    the 88f benchmark exactly.
    """
    frame = frame.copy()
    emb_cols = np.zeros((len(frame), len(GSAGE_EMBEDDING_COLUMNS)), dtype=np.float32)
    for i, addr in enumerate(frame["address"].astype(str)):
        emb_cols[i] = lookup_embedding(addr)
    for dim in range(len(GSAGE_EMBEDDING_COLUMNS)):
        frame[GSAGE_EMBEDDING_COLUMNS[dim]] = emb_cols[:, dim]
    return frame


def fit_and_save_relative_reference(train_df: pd.DataFrame) -> dict:
    """Fit the era-bucket reference on BTC TRAIN rows only and persist the artifact."""
    btc_train = train_df[train_df["chain"].astype(str) == "BTC"].copy()
    ref = fit_relative_reference(btc_train)
    save_relative_reference(ref)
    print(f"Relative-feature reference: {len(ref['era_bin_edges']) - 1} era bins over "
          f"BTC first_block [{ref['era_bin_edges'][0]:.0f}..{ref['train_max_block']:.0f}] -> {REFERENCE_PATH}")
    return ref


def _threshold_report(labels: pd.Series, probs: np.ndarray, threshold: float) -> dict:
    preds = (probs >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(labels, preds).ravel()
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    fpr = fp / max(1, fp + tn)
    return {
        "rows": int(len(labels)),
        "threshold": float(threshold),
        "precision": float(prec),
        "recall": float(rec),
        "fpr": float(fpr),
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
    }


def train_promoted_model() -> dict:
    """Train and serialize the PROMOTED 92-feature combined model (docs/ml.md).

    Config (validated by final_recommendation.py / weight_ablation.py / docs):
      92 features (72 tabular/graph + 4 entity-scale-relative + 16 GraphSAGE),
      tuned Optuna hyperparameters, scale_pos_weight=1.0 (weight ablation proved
      the tuned 4.93 was redundant on top of per-chain sample_weights), and the
      production per-chain sample_weights. The operating threshold is re-locked
      from the model's OWN validation scan (<2% FPR policy) = 0.70, with 0.85
      documented as the <1% FPR override.

    Persists:
      - artifacts/relative_features_reference.json (OOD-safe era reference)
      - artifacts/risk_model.joblib                 (92f model)
      - artifacts/risk_model_metrics.json           (metrics + locked threshold)
    """
    processed_dir = get_processed_dir()
    print(f"Loading preprocessed data from {processed_dir}")

    train_df = pd.read_csv(os.path.join(processed_dir, "train.csv"))
    val_df = pd.read_csv(os.path.join(processed_dir, "val.csv"))
    test_df = pd.read_csv(os.path.join(processed_dir, "test.csv"))

    # OOD-safe era reference (BTC train rows only) -> persisted artifact.
    fit_and_save_relative_reference(train_df)
    ref = load_relative_reference()

    # Leak-safe point-in-time graph features (Gate 2). If absent, the graph
    # columns remain dead constant-0 features (exactly the pre-fix behavior).
    snapshot_path = os.path.join(get_processed_dir(), "graph_features_snapshot.csv")
    snapshot_features = None
    if os.path.exists(snapshot_path):
        snapshot_features = pd.read_csv(snapshot_path)
        snapshot_features["address"] = snapshot_features["address"].astype(str)
        print(f"Attaching leak-safe snapshot graph features from {snapshot_path} "
              f"({len(snapshot_features):,} wallets)")
    else:
        print(f"WARN: {snapshot_path} not found — graph columns stay constant 0 (legacy behavior)")

    def transform(frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame = apply_relative_features(frame, ref)
        if snapshot_features is not None:
            # Drop the (dead) constant-0 graph columns inherited from the split
            # CSVs, then attach leak-safe point-in-time graph features computed
            # at each wallet's own last timestep (app/ml/snapshot_graph_features.py).
            frame = frame.drop(columns=[c for c in GRAPH_FEATURE_COLS if c in frame.columns])
            frame = frame.merge(
                snapshot_features[["address", *GRAPH_FEATURE_COLS]],
                on="address", how="left",
            )
            for col in GRAPH_FEATURE_COLS:
                frame[col] = frame[col].fillna(0.0).astype(np.float32)
        frame = augment_frame_with_embeddings(frame)
        return frame

    model_input_train = transform(train_df)
    model_input_val = transform(val_df)
    model_input_test = transform(test_df)
    print(f"Promoted model input: 72 tabular + 4 relative + 16 embeddings = {len(MODEL_FEATURE_COLUMNS)} columns")

    sample_weights = train_df["sample_weight"].to_numpy()
    minimum_eth_share = 0.15
    eth_train_rows = int((train_df["chain"] == "ETH").sum())
    print(f"Loaded splits: train={len(train_df):,}, val={len(val_df):,}, test={len(test_df):,}")

    assert_feature_schema(FEATURE_COLUMNS)
    assert_model_feature_schema(MODEL_FEATURE_COLUMNS)

    # Validated final config: tuned Optuna HPs + scale_pos_weight=1.0 + per-chain weights.
    clf = xgb.XGBClassifier(
        n_estimators=292, max_depth=7, learning_rate=0.11111992920245407,
        subsample=0.9172272185207363, colsample_bytree=0.7571088996592841,
        scale_pos_weight=1.0, eval_metric="logloss", random_state=42, tree_method="hist",
    )
    clf.fit(model_input_train[MODEL_FEATURE_COLUMNS].fillna(0.0), train_df["label"], sample_weight=sample_weights)
    locked_threshold, val_summary = select_best_threshold(
        val_df["label"], clf.predict_proba(model_input_val[MODEL_FEATURE_COLUMNS].fillna(0.0))[:, 1]
    )
    # Documented <1% FPR override for the promoted config.
    strict_threshold = 0.85

    chain_metrics = {
        chain: evaluate_chain_metrics(
            clf, model_input_test[model_input_test["chain"] == chain],
            locked_threshold, feature_columns=MODEL_FEATURE_COLUMNS,
        )
        for chain in ("BTC", "ETH")
    }
    eth_test = model_input_test[model_input_test["chain"] == "ETH"]
    eth_nonzero_test = eth_test[eth_test["total_txs"].fillna(0.0) > 0]
    chain_metrics["ETH_nonzero_activity_sensitivity"] = evaluate_chain_metrics(
        clf, eth_nonzero_test, locked_threshold, feature_columns=MODEL_FEATURE_COLUMNS
    )

    y_test_all = test_df["label"]
    y_prob_all = clf.predict_proba(model_input_test[MODEL_FEATURE_COLUMNS].fillna(0.0))[:, 1]
    combined_test = _threshold_report(y_test_all, y_prob_all, locked_threshold)
    combined_test["auc_pr"] = float(average_precision_score(y_test_all, y_prob_all))
    combined_test["auc_roc"] = float(roc_auc_score(y_test_all, y_prob_all))
    combined_test["f1_score"] = float(f1_score(y_test_all, (y_prob_all >= locked_threshold).astype(int)))

    def chain_btc(frame): return frame["chain"].astype(str) == "BTC"
    def chain_eth(frame): return frame["chain"].astype(str) == "ETH"

    strict_report = {
        "threshold_0.85": {
            "combined": _threshold_report(y_test_all, y_prob_all, strict_threshold),
            "btc": _threshold_report(test_df.loc[chain_btc(test_df), "label"],
                                     y_prob_all[chain_btc(test_df).to_numpy()], strict_threshold),
            "eth": _threshold_report(test_df.loc[chain_eth(test_df), "label"],
                                     y_prob_all[chain_eth(test_df).to_numpy()], strict_threshold),
        }
    }

    print(f"\n[PROMOTED 92F COMBINED TEST CONFUSION MATRIX @ threshold={locked_threshold:.2f}]")
    print(f"  {combined_test}")

    # Full SHAP importances on ETH test slice (leakage check).
    eth_test_features = eth_test[MODEL_FEATURE_COLUMNS].fillna(0.0)
    if len(eth_test_features) > 0:
        eth_shap_sample = eth_test_features.sample(n=min(2000, len(eth_test_features)), random_state=42)
        eth_shap_values = shap.TreeExplainer(clf).shap_values(eth_shap_sample)
        if isinstance(eth_shap_values, list):
            eth_shap_values = eth_shap_values[1]
        eth_full_importance = {
            col: float(np.abs(eth_shap_values[:, idx]).mean())
            for idx, col in enumerate(MODEL_FEATURE_COLUMNS)
        }
        eth_sorted = sorted(eth_full_importance.items(), key=lambda x: x[1], reverse=True)
        print("\n[ETH TEST — FULL SHAP FEATURE IMPORTANCE (top 15)]")
        for rank, (col, imp) in enumerate(eth_sorted[:15], 1):
            print(f"  {rank:>2}. {col:<40s} {imp:.6f}")
    else:
        eth_full_importance = {}

    missingness_sample = model_input_test.sample(n=min(2000, len(model_input_test)), random_state=42)
    shap_values = shap.TreeExplainer(clf).shap_values(missingness_sample[MODEL_FEATURE_COLUMNS].fillna(0.0))
    if isinstance(shap_values, list):
        shap_values = shap_values[1]
    missingness_importance = {
        column: float(np.abs(shap_values[:, FEATURE_COLUMNS.index(column)]).mean())
        for column in MISSING_INDICATOR_COLUMNS
    }
    print("\nMissingness-indicator SHAP importance:")
    print(json.dumps(missingness_importance, indent=2))
    print("Per-chain held-out metrics:")
    print(json.dumps(chain_metrics, indent=2))

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    report = {
        "model": "xgboost_combined_btc_eth_graphsage92",
        "feature_count": len(MODEL_FEATURE_COLUMNS),
        "tabular_feature_count": len(FEATURE_COLUMNS),
        "embedding_feature_count": len(GSAGE_EMBEDDING_COLUMNS),
        "relative_feature_count": len(RELATIVE_FEATURE_COLUMNS),
        "relative_features": RELATIVE_FEATURE_COLUMNS,
        "embedding_mode": "precomputed_wallet_embeddings_npz",
        "relative_reference": "relative_features_reference.json (BTC-train OOD-safe era fit)",
        "locked_threshold": locked_threshold,
        "threshold_decision": {
            "lock": locked_threshold,
            "policy": "highest val recall with combined val FPR < 2%",
            "fpr1pc_override": strict_threshold,
            "note": "0.70 = promoted operating point (<2% FPR cap); 0.85 = documented <1% FPR override (docs/ml.md).",
        },
        "class_weighting": {"strategy": "per_chain_sample_weight", "minimum_eth_train_share": minimum_eth_share},
        "hyperparameters": {
            "learning_rate": 0.11111992920245407, "max_depth": 7, "n_estimators": 292,
            "subsample": 0.9172272185207363, "colsample_bytree": 0.7571088996592841,
            "scale_pos_weight": 1.0,
        },
        "manual_audit": {
            "eth_zero_activity_test_rows": int((eth_test["total_txs"].fillna(0.0) == 0).sum()),
            "eth_zero_activity_test_fraud_rows": int(((eth_test["total_txs"].fillna(0.0) == 0) & (eth_test["label"] == 1)).sum()),
        },
        "validation": val_summary,
        "combined_test": combined_test,
        "chain_metrics": chain_metrics,
        "strict_fpr1pc_threshold": strict_report,
        "missingness_indicator_shap_importance": missingness_importance,
        "eth_test_full_shap_importance": eth_full_importance,
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as metrics_file:
        json.dump(report, metrics_file, indent=2)
    print(f"\nSaved {MODEL_PATH} and {METRICS_PATH}")
    return report


def train_combined_model() -> dict:
    """Retrain the promoted combined model (kept as the canonical auto-retrain entrypoint).

    ``app/ml/model.py`` calls this when the artifact is missing; it now produces
    the same validated 92-feature promoted config as ``train_promoted_model``.
    """
    return train_promoted_model()
def select_best_threshold(
    y_val: pd.Series,
    y_prob_val: np.ndarray,
    candidate_thresholds: list[float] = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95],
    max_fpr: float = 0.020,
) -> tuple[float, dict]:
    """
    Select optimal classification threshold on VALIDATION SLICE ONLY (Time steps 30..34).
    Finds threshold that maximizes Recall subject to FPR < max_fpr (2.0%).
    """
    print("\n[VALIDATION SLICE THRESHOLD SCAN (Time Steps 30..34)]")
    print(f"{'Threshold':>10} | {'Precision':>10} | {'Recall':>10} | {'FPR':>10} | {'FPR < 2%':>8}")
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
    Train XGBoost on real Elliptic++ temporal split with separate validation slice for threshold tuning.
      1. Train: Time steps 1..29
      2. Validation: Time steps 30..34 (Threshold optimization)
      3. Test: Time steps 35..49 (Untouched holdout evaluation)
    """
    # Deduplicate rows after join
    df = pd.merge(df_features, df_classes, on="address")
    initial_len = len(df)
    df = df.drop_duplicates()  # remove exact-copy rows first
    df = df.drop_duplicates(subset=["address"], keep="last").copy()
    print(f"Deduplication on address: {initial_len:,} -> {len(df):,} rows.")

    # Filter out unknown class (class 3) — train on labeled illicit (1) and licit (2)
    df = df[df["class"].isin([1, 2])].copy()
    df["label"] = (df["class"] == 1).astype(int)
    print(f"Filtered to labeled actors (Class 1 & 2): {len(df):,} total actors (Illicit: {df['label'].sum():,}, Licit: {(df['label'] == 0).sum():,}).")

    # 3-Way Temporal Partitioning
    train_mask = df["Time step"] <= 29
    val_mask = (df["Time step"] >= 30) & (df["Time step"] <= 34)
    test_mask = df["Time step"] >= 35

    train_df = df[train_mask].copy()
    val_df = df[val_mask].copy()
    test_df = df[test_mask].copy()

    train_addrs = set(train_df["address"].tolist())
    val_addrs = set(val_df["address"].tolist())
    test_addrs = set(test_df["address"].tolist())

    # Assert 0 address overlap across all 3 sets
    assert len(train_addrs.intersection(val_addrs)) == 0, "Address overlap between Train and Val!"
    assert len(train_addrs.intersection(test_addrs)) == 0, "Address overlap between Train and Test!"
    assert len(val_addrs.intersection(test_addrs)) == 0, "Address overlap between Val and Test!"

    print("\n" + "=" * 60)
    print("      REAL ELLIPTIC++ TEMPORAL PARTITIONING AUDIT")
    print("=" * 60)
    print(f"  Train: steps 1..29  (N={len(train_df):,}, Illicit={train_df['label'].sum():,}, BaseRate={train_df['label'].mean():.2%})")
    print(f"  Val:   steps 30..34 (N={len(val_df):,}, Illicit={val_df['label'].sum():,}, BaseRate={val_df['label'].mean():.2%})")
    print(f"  Test:  steps 35..49 (N={len(test_df):,}, Illicit={test_df['label'].sum():,}, BaseRate={test_df['label'].mean():.2%})")
    print("=" * 60)

    # Assert feature schema (exact order and names)
    assert_feature_schema(FEATURE_COLUMNS)

    X_train = canonicalize_training_features(train_df).fillna(0.0)
    y_train = train_df["label"]

    X_val = canonicalize_training_features(val_df).fillna(0.0)
    y_val = val_df["label"]

    X_test = canonicalize_training_features(test_df).fillna(0.0)
    y_test = test_df["label"]

    # Handle class imbalance via scale_pos_weight
    scale_pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())

    print(f"\nTraining XGBoost Classifier (scale_pos_weight={scale_pos_weight:.2f})...")
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
    clf.fit(X_train, y_train)

    # Threshold Selection on Validation Slice ONLY (Time steps 30..34)
    y_prob_val = clf.predict_proba(X_val)[:, 1]
    locked_threshold, val_metrics = select_best_threshold(y_val, y_prob_val)

    val_prec_curve, val_rec_curve, _ = precision_recall_curve(y_val, y_prob_val)
    val_auc_pr = auc(val_rec_curve, val_prec_curve)
    val_auc_roc = roc_auc_score(y_val, y_prob_val)
    val_brier = brier_score_loss(y_val, y_prob_val)

    # Single Out-of-Sample Evaluation on UNTOUCHED Test Set (Time steps 35..49)
    y_prob_test = clf.predict_proba(X_test)[:, 1]
    y_pred_test = (y_prob_test >= locked_threshold).astype(int)

    test_prec_curve, test_rec_curve, _ = precision_recall_curve(y_test, y_prob_test)
    test_auc_pr = auc(test_rec_curve, test_prec_curve)
    test_auc_roc = roc_auc_score(y_test, y_prob_test)
    test_brier = brier_score_loss(y_test, y_prob_test)

    validation_metrics = evaluate_model(
        clf, X_val, y_val, locked_threshold, "validation"
    )
    test_metrics = evaluate_model(clf, X_test, y_test, locked_threshold, "test")

    tn, fp, fn, tp = confusion_matrix(y_test, y_pred_test).ravel()
    test_prec = tp / max(1, (tp + fp))
    test_rec = tp / max(1, (tp + fn))
    test_fpr = fp / max(1, (fp + tn))

    print("\n" + "=" * 65)
    print("  PHASE 4: REAL ELLIPTIC++ OUT-OF-SAMPLE TEST EVALUATION (STEPS 35..49)")
    print("=" * 65)
    print(f"  Locked Threshold:     {locked_threshold:.2f}")
    print(f"  1. AUC-PR (Primary):  {test_auc_pr:.4f} (Val: {val_auc_pr:.4f})")
    print(f"  2. Precision:         {test_prec:.4f} (TP={tp:,}, FP={fp:,})")
    print(f"     Recall:            {test_rec:.4f} (FN={fn:,})")
    print(f"  3. FPR:               {test_fpr:.4f} ({test_fpr * 100:.2f}%)")
    print(f"  4. AUC-ROC:           {test_auc_roc:.4f} (Val: {val_auc_roc:.4f})")
    print(f"  5. Brier Score:       {test_brier:.4f} (Val: {val_brier:.4f})")
    print("=" * 65 + "\n")

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    joblib.dump(clf, MODEL_PATH)
    print(f"Saved trained real XGBoost model to {MODEL_PATH}")

    metrics_report = {
        "model": "xgboost",
        "feature_count": len(FEATURE_COLUMNS),
        "class_weighting": {
            "strategy": "scale_pos_weight",
            "value": float(scale_pos_weight),
            "formula": "licit_training_rows / illicit_training_rows",
        },
        "feature_schema": FEATURE_COLUMNS,
        "validation": validation_metrics,
        "test": test_metrics,
        "legacy_metrics": {
            "validation_auc_pr": val_auc_pr,
            "validation_brier": val_brier,
            "test_auc_pr": test_auc_pr,
            "test_fpr": test_fpr,
            "test_brier": test_brier,
        },
    }
    with open(METRICS_PATH, "w", encoding="utf-8") as metrics_file:
        json.dump(metrics_report, metrics_file, indent=2)
    print(f"Saved model metrics report to {METRICS_PATH}")

    # Re-initialize caches
    from app.ml.explain import clear_explainer_cache
    from app.ml.model import clear_model_cache
    clear_explainer_cache()
    clear_model_cache()

    return {
        "locked_threshold": locked_threshold,
        "test_auc_pr": test_auc_pr,
        "test_precision": test_prec,
        "test_recall": test_rec,
        "test_fpr": test_fpr,
        "test_auc_roc": test_auc_roc,
        "test_brier": test_brier,
        "metrics_report": metrics_report,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train XGBoost model on combined BTC + ETH datasets")
    parser.add_argument("--preprocess", action="store_true", help="Run preprocessing pipeline (writes data/processed/)")
    parser.add_argument("--prepare-combined", action="store_true", help="(deprecated) Build and report BTC + ETH rows without training")
    args = parser.parse_args()

    if args.preprocess:
        from app.ml.preprocess import run_preprocessing
        run_preprocessing()
        raise SystemExit(0)

    if args.prepare_combined:
        build_combined_training_dataframe()
        raise SystemExit(0)

    train_combined_model()
