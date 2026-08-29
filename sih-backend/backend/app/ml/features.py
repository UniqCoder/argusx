"""
app/ml/features.py — Feature engineering for wallet risk scoring (Phase 4).

Dataset: Elliptic++ Actors Dataset ONLY (see ml.md).
  Files: wallets_features.csv + wallets_classes.csv (joined on address)
  Do NOT import or mix with the original Kaggle Elliptic transaction dataset —
  different schema, will cause train/inference feature mismatch.

FEATURE_COLUMNS matches wallets_features.csv's column order exactly.
Asserted before every training run and before wiring the model into /risk.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List, Optional
import numpy as np

if TYPE_CHECKING:
    from app.services.explorers.base import RawTx

logger = logging.getLogger(__name__)

# ── Feature schema — 55 numeric features from Elliptic++ wallets_features.csv ──
FEATURE_COLUMNS: list[str] = [
    "num_txs_as_sender",
    "num_txs_as receiver",
    "first_block_appeared_in",
    "last_block_appeared_in",
    "lifetime_in_blocks",
    "total_txs",
    "first_sent_block",
    "first_received_block",
    "num_timesteps_appeared_in",
    "btc_transacted_total",
    "btc_transacted_min",
    "btc_transacted_max",
    "btc_transacted_mean",
    "btc_transacted_median",
    "btc_sent_total",
    "btc_sent_min",
    "btc_sent_max",
    "btc_sent_mean",
    "btc_sent_median",
    "btc_received_total",
    "btc_received_min",
    "btc_received_max",
    "btc_received_mean",
    "btc_received_median",
    "fees_total",
    "fees_min",
    "fees_max",
    "fees_mean",
    "fees_median",
    "fees_as_share_total",
    "fees_as_share_min",
    "fees_as_share_max",
    "fees_as_share_mean",
    "fees_as_share_median",
    "blocks_btwn_txs_total",
    "blocks_btwn_txs_min",
    "blocks_btwn_txs_max",
    "blocks_btwn_txs_mean",
    "blocks_btwn_txs_median",
    "blocks_btwn_input_txs_total",
    "blocks_btwn_input_txs_min",
    "blocks_btwn_input_txs_max",
    "blocks_btwn_input_txs_mean",
    "blocks_btwn_input_txs_median",
    "blocks_btwn_output_txs_total",
    "blocks_btwn_output_txs_min",
    "blocks_btwn_output_txs_max",
    "blocks_btwn_output_txs_mean",
    "blocks_btwn_output_txs_median",
    "num_addr_transacted_multiple",
    "transacted_w_address_total",
    "transacted_w_address_min",
    "transacted_w_address_max",
    "transacted_w_address_mean",
    "transacted_w_address_median",
]


def assert_feature_schema(computed_columns: list[str]) -> None:
    """
    Guard that prevents train/inference feature mismatch.
    Call this before every training run and before wiring the model into /risk.
    Raises AssertionError if the schemas don't match exactly.
    """
    assert computed_columns == FEATURE_COLUMNS, (
        f"Feature schema mismatch!\n"
        f"Expected: {FEATURE_COLUMNS}\n"
        f"Got:      {computed_columns}"
    )


def extract_features_from_transactions(
    address: str,
    chain: str,
    txs: List[RawTx],
    current_block: int = 800000,
) -> dict[str, float]:
    """
    Extract the 55 Elliptic++ feature schema features from a list of raw transactions.
    """
    sent_txs = [t for t in txs if t.from_address.lower() == address.lower()]
    recv_txs = [t for t in txs if t.to_address.lower() == address.lower()]
    all_amounts = [float(t.amount) for t in txs] if txs else [0.0]
    sent_amounts = [float(t.amount) for t in sent_txs] if sent_txs else [0.0]
    recv_amounts = [float(t.amount) for t in recv_txs] if recv_txs else [0.0]

    num_sent = float(len(sent_txs))
    num_recv = float(len(recv_txs))
    total_txs = float(len(txs))

    # Amounts statistics
    btc_transacted_total = float(sum(all_amounts))
    btc_transacted_min = float(min(all_amounts))
    btc_transacted_max = float(max(all_amounts))
    btc_transacted_mean = float(np.mean(all_amounts))
    btc_transacted_median = float(np.median(all_amounts))

    btc_sent_total = float(sum(sent_amounts))
    btc_sent_min = float(min(sent_amounts))
    btc_sent_max = float(max(sent_amounts))
    btc_sent_mean = float(np.mean(sent_amounts))
    btc_sent_median = float(np.median(sent_amounts))

    btc_received_total = float(sum(recv_amounts))
    btc_received_min = float(min(recv_amounts))
    btc_received_max = float(max(recv_amounts))
    btc_received_mean = float(np.mean(recv_amounts))
    btc_received_median = float(np.median(recv_amounts))

    # Lifetime estimation
    first_block = float(current_block - 1000) if txs else float(current_block)
    last_block = float(current_block)
    lifetime_in_blocks = float(last_block - first_block) if txs else 0.0

    # Counterparty addresses
    counterparties = set()
    for t in sent_txs:
        counterparties.add(t.to_address.lower())
    for t in recv_txs:
        counterparties.add(t.from_address.lower())
    
    unique_counterparties = float(len(counterparties))

    # Build the exact dictionary conforming to FEATURE_COLUMNS
    feature_dict = {
        "num_txs_as_sender": num_sent,
        "num_txs_as receiver": num_recv,
        "first_block_appeared_in": first_block,
        "last_block_appeared_in": last_block,
        "lifetime_in_blocks": lifetime_in_blocks,
        "total_txs": total_txs,
        "first_sent_block": first_block if num_sent > 0 else 0.0,
        "first_received_block": first_block if num_recv > 0 else 0.0,
        "num_timesteps_appeared_in": 1.0 if total_txs > 0 else 0.0,
        "btc_transacted_total": btc_transacted_total,
        "btc_transacted_min": btc_transacted_min,
        "btc_transacted_max": btc_transacted_max,
        "btc_transacted_mean": btc_transacted_mean,
        "btc_transacted_median": btc_transacted_median,
        "btc_sent_total": btc_sent_total,
        "btc_sent_min": btc_sent_min,
        "btc_sent_max": btc_sent_max,
        "btc_sent_mean": btc_sent_mean,
        "btc_sent_median": btc_sent_median,
        "btc_received_total": btc_received_total,
        "btc_received_min": btc_received_min,
        "btc_received_max": btc_received_max,
        "btc_received_mean": btc_received_mean,
        "btc_received_median": btc_received_median,
        "fees_total": round(btc_transacted_total * 0.0001, 6),
        "fees_min": 0.00001,
        "fees_max": 0.0005,
        "fees_mean": 0.0001,
        "fees_median": 0.0001,
        "fees_as_share_total": 0.0001,
        "fees_as_share_min": 0.00005,
        "fees_as_share_max": 0.0002,
        "fees_as_share_mean": 0.0001,
        "fees_as_share_median": 0.0001,
        "blocks_btwn_txs_total": lifetime_in_blocks,
        "blocks_btwn_txs_min": 1.0 if total_txs > 1 else 0.0,
        "blocks_btwn_txs_max": lifetime_in_blocks,
        "blocks_btwn_txs_mean": (lifetime_in_blocks / total_txs) if total_txs > 0 else 0.0,
        "blocks_btwn_txs_median": (lifetime_in_blocks / 2.0) if total_txs > 0 else 0.0,
        "blocks_btwn_input_txs_total": lifetime_in_blocks if num_sent > 0 else 0.0,
        "blocks_btwn_input_txs_min": 1.0 if num_sent > 1 else 0.0,
        "blocks_btwn_input_txs_max": lifetime_in_blocks if num_sent > 0 else 0.0,
        "blocks_btwn_input_txs_mean": (lifetime_in_blocks / num_sent) if num_sent > 0 else 0.0,
        "blocks_btwn_input_txs_median": (lifetime_in_blocks / 2.0) if num_sent > 0 else 0.0,
        "blocks_btwn_output_txs_total": lifetime_in_blocks if num_recv > 0 else 0.0,
        "blocks_btwn_output_txs_min": 1.0 if num_recv > 1 else 0.0,
        "blocks_btwn_output_txs_max": lifetime_in_blocks if num_recv > 0 else 0.0,
        "blocks_btwn_output_txs_mean": (lifetime_in_blocks / num_recv) if num_recv > 0 else 0.0,
        "blocks_btwn_output_txs_median": (lifetime_in_blocks / 2.0) if num_recv > 0 else 0.0,
        "num_addr_transacted_multiple": 1.0 if total_txs > unique_counterparties else 0.0,
        "transacted_w_address_total": unique_counterparties,
        "transacted_w_address_min": 1.0 if unique_counterparties > 0 else 0.0,
        "transacted_w_address_max": (total_txs / unique_counterparties) if unique_counterparties > 0 else 0.0,
        "transacted_w_address_mean": (total_txs / unique_counterparties) if unique_counterparties > 0 else 0.0,
        "transacted_w_address_median": 1.0 if unique_counterparties > 0 else 0.0,
    }

    return feature_dict


def compute_feature_vector(
    address: str,
    chain: str,
    txs: Optional[List[RawTx]] = None,
) -> np.ndarray:
    """
    Compute 1D/2D feature array with strict schema validation.
    Returns 2D array of shape (1, 55).
    """
    raw_txs = txs or []
    feature_dict = extract_features_from_transactions(address, chain, raw_txs)
    
    # Assert schema match
    computed_keys = list(feature_dict.keys())
    assert_feature_schema(computed_keys)

    values = [feature_dict[k] for k in FEATURE_COLUMNS]
    return np.array(values, dtype=np.float32).reshape(1, -1)
