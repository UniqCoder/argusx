"""
app/ml/preprocess.py — Preprocess raw Elliptic++ and Ethereum Fraud datasets
into training-ready splits at data/processed/.

Pipeline:
  1. Load BTC wallets_features.csv + wallets_classes.csv
  2. Full-row dedup → address-level dedup (keep last timestep)
  3. Filter to class 1 (illicit) and 2 (licit), drop class 3
  4. Canonicalize BTC feature names → FEATURE_COLUMNS schema
  5. Load ETH transaction_dataset.csv, map to canonical schema
  6. BTC temporal split (train ≤29, val 30-34, test ≥35)
  7. ETH stratified split (70/15/15)
  8. Combine per-split, enforce min 15% ETH train share
  9. Compute per-chain sample weights for train split
  10. Write train.csv, val.csv, test.csv, btc_unlabeled.csv
  11. Generate preprocessing_report.md
"""
import logging
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from app.ml.features import FEATURE_COLUMNS, assert_feature_schema
from app.ml.train import (
    DATASET_TO_CANONICAL_RENAME,
    add_missing_indicators,
    build_per_chain_sample_weights,
    get_data_dir,
    get_ethereum_fraud_path,
    load_ethereum_fraud_dataset,
    load_real_elliptic_dataset,
    stratified_chain_split,
)

logger = logging.getLogger(__name__)

PROCESSED_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "data", "processed"
)
PROCESSED_DIR = os.path.abspath(PROCESSED_DIR)


def preprocess_btc(
    btc_features: pd.DataFrame,
    btc_classes: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Process raw BTC Elliptic++ data:
      - Merge features + classes
      - Full-row dedup (remove 347K exact copies)
      - Address-level dedup (keep last timestep)
      - Split labeled (class 1,2) vs unlabeled (class 3)
      - Canonicalize feature names → FEATURE_COLUMNS schema

    Returns:
        (labeled_df, unlabeled_df, cleaning_counts) where each df has columns:
        FEATURE_COLUMNS + address, chain, label, time_step
        and cleaning_counts is a dict with dedup statistics.
    """
    logger.info("Processing BTC Elliptic++ data...")
    logger.info(
        "Raw: features=%d rows, classes=%d rows",
        len(btc_features), len(btc_classes),
    )

    merged = pd.merge(btc_features, btc_classes[["address", "class"]], on="address")
    n_before = len(merged)

    merged = merged.drop_duplicates()
    n_after_full_dedup = len(merged)
    n_full_dupes = n_before - n_after_full_dedup
    logger.info("Full-row dedup: %d → %d (removed %d exact copies)", n_before, n_after_full_dedup, n_full_dupes)

    merged = merged.drop_duplicates(subset=["address"], keep="last")
    n_after_addr_dedup = len(merged)
    logger.info("Address dedup (keep last timestep): %d → %d", n_after_full_dedup, n_after_addr_dedup)

    # Split labeled vs unlabeled
    labeled_mask = merged["class"].isin([1, 2])
    unlabeled_mask = merged["class"] == 3

    labeled_raw = merged[labeled_mask].copy()
    unlabeled_raw = merged[unlabeled_mask].copy()

    logger.info(
        "Class distribution — labeled: %d (illicit=%d, licit=%d), unlabeled: %d",
        len(labeled_raw),
        int((labeled_raw["class"] == 1).sum()),
        int((labeled_raw["class"] == 2).sum()),
        len(unlabeled_raw),
    )

    # Canonicalize labeled data
    labeled = labeled_raw.copy()
    labeled_canonical = labeled.rename(columns=DATASET_TO_CANONICAL_RENAME)
    missing = [c for c in FEATURE_COLUMNS if c not in labeled_canonical.columns]
    if missing:
        labeled_canonical = labeled_canonical.assign(**{c: np.nan for c in missing})
    labeled_canonical = add_missing_indicators(labeled_canonical)
    labeled_canonical = labeled_canonical[FEATURE_COLUMNS].copy()
    labeled_canonical["address"] = labeled["address"].astype(str).str.lower().values
    labeled_canonical["chain"] = "BTC"
    labeled_canonical["label"] = (labeled["class"].to_numpy() == 1).astype(int)
    labeled_canonical["time_step"] = labeled["Time step"].to_numpy()

    assert_feature_schema(FEATURE_COLUMNS)

    # Canonicalize unlabeled data (for inference scoring)
    unlabeled = unlabeled_raw.copy()
    unlabeled_canonical = unlabeled.rename(columns=DATASET_TO_CANONICAL_RENAME)
    missing_u = [c for c in FEATURE_COLUMNS if c not in unlabeled_canonical.columns]
    if missing_u:
        unlabeled_canonical = unlabeled_canonical.assign(**{c: np.nan for c in missing_u})
    unlabeled_canonical = add_missing_indicators(unlabeled_canonical)
    unlabeled_canonical = unlabeled_canonical[FEATURE_COLUMNS].copy()
    unlabeled_canonical["address"] = unlabeled["address"].astype(str).str.lower().values
    unlabeled_canonical["chain"] = "BTC"
    unlabeled_canonical["time_step"] = unlabeled["Time step"].to_numpy()

    logger.info(
        "BTC labeled: %d rows, unlabeled (class 3): %d rows",
        len(labeled_canonical), len(unlabeled_canonical),
    )

    cleaning_counts = {
        "full_row_dupes": n_full_dupes,
        "after_full_dedup": n_after_full_dedup,
        "after_addr_dedup": n_after_addr_dedup,
    }

    return labeled_canonical, unlabeled_canonical, cleaning_counts


def preprocess_eth() -> pd.DataFrame:
    """
    Load and canonicalize the Ethereum fraud dataset.
    Already returns FEATURE_COLUMNS + address, chain, label.
    """
    logger.info("Processing Ethereum fraud dataset...")
    eth = load_ethereum_fraud_dataset()
    eth["time_step"] = np.nan

    n_fraud = int((eth["label"] == 1).sum())
    n_legit = int((eth["label"] == 0).sum())
    logger.info("ETH labeled: %d rows (fraud=%d, legit=%d)", len(eth), n_fraud, n_legit)

    assert_feature_schema(FEATURE_COLUMNS)
    return eth


def split_and_combine(
    btc_labeled: pd.DataFrame,
    eth_labeled: pd.DataFrame,
    min_eth_share: float = 0.15,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split BTC temporally, ETH stratified-random, combine per-split.

    Returns (train_df, val_df, test_df) with columns:
    FEATURE_COLUMNS + address, chain, label, time_step, sample_weight (train only)
    """
    btc_train = btc_labeled[btc_labeled["time_step"] <= 29].copy()
    btc_val = btc_labeled[btc_labeled["time_step"].between(30, 34)].copy()
    btc_test = btc_labeled[btc_labeled["time_step"] >= 35].copy()

    eth_train, eth_val, eth_test = stratified_chain_split(eth_labeled)

    logger.info(
        "BTC splits — train: %d, val: %d, test: %d",
        len(btc_train), len(btc_val), len(btc_test),
    )
    logger.info(
        "ETH splits — train: %d, val: %d, test: %d",
        len(eth_train), len(eth_val), len(eth_test),
    )

    train_df = pd.concat([btc_train, eth_train], ignore_index=True)

    # Enforce minimum ETH share in training set
    required_eth = int(np.ceil(len(btc_train) * min_eth_share / (1 - min_eth_share)))
    if len(eth_train) < required_eth:
        eth_train = eth_train.sample(n=required_eth, replace=True, random_state=42)
        train_df = pd.concat([btc_train, eth_train], ignore_index=True)
        logger.info("ETH oversampled to %d rows (min share %.0f%%)", len(eth_train), min_eth_share * 100)

    val_df = pd.concat([btc_val, eth_val], ignore_index=True)
    test_df = pd.concat([btc_test, eth_test], ignore_index=True)

    # Compute per-chain sample weights for training set
    sample_weights = build_per_chain_sample_weights(train_df)
    train_df = train_df.copy()
    train_df["sample_weight"] = sample_weights

    btc_w = sample_weights[train_df["chain"].to_numpy() == "BTC"].sum()
    eth_w = sample_weights[train_df["chain"].to_numpy() == "ETH"].sum()
    logger.info(
        "Train: %d rows (ETH share %.1f%%), sample weights BTC=%.2f ETH=%.2f",
        len(train_df),
        len(eth_train) / len(train_df) * 100,
        btc_w, eth_w,
    )

    return train_df, val_df, test_df


def write_outputs(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    test_df: pd.DataFrame,
    btc_unlabeled: pd.DataFrame,
    report: dict,
) -> None:
    """Write preprocessed CSVs and preprocessing_report.md to data/processed/."""
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    train_path = os.path.join(PROCESSED_DIR, "train.csv")
    val_path = os.path.join(PROCESSED_DIR, "val.csv")
    test_path = os.path.join(PROCESSED_DIR, "test.csv")
    unlabeled_path = os.path.join(PROCESSED_DIR, "btc_unlabeled.csv")

    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)
    test_df.to_csv(test_path, index=False)
    btc_unlabeled.to_csv(unlabeled_path, index=False)

    logger.info("Wrote %s (%d rows)", train_path, len(train_df))
    logger.info("Wrote %s (%d rows)", val_path, len(val_df))
    logger.info("Wrote %s (%d rows)", test_path, len(test_df))
    logger.info("Wrote %s (%d rows)", unlabeled_path, len(btc_unlabeled))

    # Write preprocessing_report.md
    report_path = os.path.join(PROCESSED_DIR, "preprocessing_report.md")
    _write_report(report_path, report)
    logger.info("Wrote %s", report_path)


def _write_report(path: str, report: dict) -> None:
    """Generate preprocessing_report.md from collected metadata."""
    lines = [
        "# Preprocessing Report",
        f"Generated: {report['timestamp']}",
        "",
        "## Raw Input",
        f"- BTC wallets_features.csv: {report['raw']['btc_features_rows']:,} rows",
        f"- BTC wallets_classes.csv: {report['raw']['btc_classes_rows']:,} rows "
        f"(illicit={report['raw']['btc_illicit']:,}, "
        f"licit={report['raw']['btc_licit']:,}, "
        f"unknown={report['raw']['btc_unknown']:,})",
        f"- ETH transaction_dataset.csv: {report['raw']['eth_rows']:,} rows "
        f"(fraud={report['raw']['eth_fraud']:,}, "
        f"legit={report['raw']['eth_legit']:,})",
        "",
        "## Cleaning",
        f"- Full-row duplicates removed: {report['cleaning']['full_row_dupes']:,}",
        f"- Address-level dedup (keep last timestep): "
        f"{report['cleaning']['after_full_dedup']:,} → {report['cleaning']['after_addr_dedup']:,}",
        f"- Class 3 (unknown) dropped from training: {report['cleaning']['class3_dropped']:,}",
        f"- BTC labeled training rows: {report['cleaning']['btc_labeled']:,} "
        f"(illicit={report['cleaning']['btc_illicit']:,}, "
        f"licit={report['cleaning']['btc_licit']:,})",
        f"- ETH labeled training rows: {report['cleaning']['eth_labeled']:,} "
        f"(fraud={report['cleaning']['eth_fraud']:,}, "
        f"legit={report['cleaning']['eth_legit']:,})",
        "",
        "## Feature Schema",
        f"- Canonical columns: {len(FEATURE_COLUMNS)} "
        f"(62 base + 7 missingness indicators + 3 graph features)",
        f"- BTC features mapped via DATASET_TO_CANONICAL_RENAME "
        f"({report['schema']['btc_renames']} renames, "
        f"{report['schema']['btc_unchanged']} unchanged)",
        "- ETH features mapped via Kaggle → canonical direct_map + derived features",
        "- Unavailable BTC features on ETH: null-imputed + missingness indicators",
        "",
        "## Splits",
        "| Split | BTC rows | ETH rows | Total | Illicit% |",
        "|-------|----------|----------|-------|----------|",
    ]

    for split_name in ("train", "val", "test"):
        s = report["splits"][split_name]
        illicit_pct = s["illicit"] / max(s["total"], 1) * 100
        lines.append(
            f"| {split_name.capitalize()} | {s['btc']:,} | {s['eth']:,} | "
            f"{s['total']:,} | {illicit_pct:.1f}% |"
        )

    lines += [
        "",
        "- BTC split: temporal (train ≤29, val 30-34, test ≥35)",
        "- ETH split: stratified random 70/15/15",
        f"- Min ETH train share: {report['split_config']['min_eth_share']:.0%} "
        "(oversampled if needed)",
        "- Per-chain sample weights: class-balanced within chain, equal mass across chains",
        "",
        "## Outputs",
        f"- data/processed/train.csv: {report['splits']['train']['total']:,} rows, "
        "76 cols (72 features + address/chain/label/time_step/sample_weight)",
        f"- data/processed/val.csv: {report['splits']['val']['total']:,} rows, "
        "75 cols (no sample_weight)",
        f"- data/processed/test.csv: {report['splits']['test']['total']:,} rows, "
        "75 cols (no sample_weight)",
        f"- data/processed/btc_unlabeled.csv: {report['cleaning']['class3_dropped']:,} rows "
        "(class 3 BTC wallets for inference reference)",
        "",
    ]

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def run_preprocessing() -> dict:
    """Run the full preprocessing pipeline. Returns the report dict."""
    logger.info("=" * 60)
    logger.info("PREPROCESSING PIPELINE START")
    logger.info("=" * 60)

    btc_features, btc_classes = load_real_elliptic_dataset(get_data_dir())

    btc_labeled, btc_unlabeled, cleaning_counts = preprocess_btc(btc_features, btc_classes)
    eth_labeled = preprocess_eth()

    train_df, val_df, test_df = split_and_combine(btc_labeled, eth_labeled)

    # Collect report metadata
    report = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "raw": {
            "btc_features_rows": len(btc_features),
            "btc_classes_rows": len(btc_classes),
            "btc_illicit": int((btc_classes["class"] == 1).sum()),
            "btc_licit": int((btc_classes["class"] == 2).sum()),
            "btc_unknown": int((btc_classes["class"] == 3).sum()),
            "eth_rows": len(eth_labeled),
            "eth_fraud": int((eth_labeled["label"] == 1).sum()),
            "eth_legit": int((eth_labeled["label"] == 0).sum()),
        },
        "cleaning": {
            "full_row_dupes": cleaning_counts["full_row_dupes"],
            "after_full_dedup": cleaning_counts["after_full_dedup"],
            "after_addr_dedup": cleaning_counts["after_addr_dedup"],
            "class3_dropped": int(len(btc_unlabeled)),
            "btc_labeled": len(btc_labeled),
            "btc_illicit": int((btc_labeled["label"] == 1).sum()),
            "btc_licit": int((btc_labeled["label"] == 0).sum()),
            "eth_labeled": len(eth_labeled),
            "eth_fraud": int((eth_labeled["label"] == 1).sum()),
            "eth_legit": int((eth_labeled["label"] == 0).sum()),
        },
        "schema": {
            "btc_renames": sum(1 for k, v in DATASET_TO_CANONICAL_RENAME.items() if k != v),
            "btc_unchanged": sum(1 for k, v in DATASET_TO_CANONICAL_RENAME.items() if k == v),
        },
        "splits": {
            "train": {
                "btc": int((train_df["chain"] == "BTC").sum()),
                "eth": int((train_df["chain"] == "ETH").sum()),
                "total": len(train_df),
                "illicit": int(train_df["label"].sum()),
            },
            "val": {
                "btc": int((val_df["chain"] == "BTC").sum()),
                "eth": int((val_df["chain"] == "ETH").sum()),
                "total": len(val_df),
                "illicit": int(val_df["label"].sum()),
            },
            "test": {
                "btc": int((test_df["chain"] == "BTC").sum()),
                "eth": int((test_df["chain"] == "ETH").sum()),
                "total": len(test_df),
                "illicit": int(test_df["label"].sum()),
            },
        },
        "split_config": {
            "min_eth_share": 0.15,
        },
    }

    write_outputs(train_df, val_df, test_df, btc_unlabeled, report)

    logger.info("=" * 60)
    logger.info("PREPROCESSING PIPELINE COMPLETE")
    logger.info("=" * 60)

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    run_preprocessing()
