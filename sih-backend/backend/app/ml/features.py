"""
app/ml/features.py — Feature engineering for wallet risk scoring (Phase 4).

Dataset: Elliptic++ Actors Dataset schema plus chain-native inference features plus engineered
graph topology features (65 numeric features total: 55 tabular + 7 missing indicators + 3 graph).
Extracts graph topology, volume, temporal, and counterparty features from live blockchain transactions.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, List, Optional
import numpy as np

if TYPE_CHECKING:
    from app.services.explorers.base import RawTx

logger = logging.getLogger(__name__)

# ── Feature schema — 55 numeric features from Elliptic++ wallets_features.csv ──
FEATURE_COLUMNS: list[str] = [
    "num_txs_as_sender",
    "num_txs_as_receiver",
    "first_block_appeared_in",
    "last_block_appeared_in",
    "lifetime_in_blocks",
    "total_txs",
    "first_sent_block",
    "first_received_block",
    "num_timesteps_appeared_in",
    "value_transacted_total",
    "value_transacted_min",
    "value_transacted_max",
    "value_transacted_mean",
    "value_transacted_median",
    "value_sent_total",
    "value_sent_min",
    "value_sent_max",
    "value_sent_mean",
    "value_sent_median",
    "value_received_total",
    "value_received_min",
    "value_received_max",
    "value_received_mean",
    "value_received_median",
    "chain_fee_total",
    "chain_fee_min",
    "chain_fee_max",
    "chain_fee_mean",
    "chain_fee_median",
    "fee_ratio_total",
    "fee_ratio_min",
    "fee_ratio_max",
    "fee_ratio_mean",
    "fee_ratio_median",
    "time_between_txs_total",
    "time_between_txs_min",
    "time_between_txs_max",
    "time_between_txs_mean",
    "time_between_txs_median",
    "time_between_input_txs_total",
    "time_between_input_txs_min",
    "time_between_input_txs_max",
    "time_between_input_txs_mean",
    "time_between_input_txs_median",
    "time_between_output_txs_total",
    "time_between_output_txs_min",
    "time_between_output_txs_max",
    "time_between_output_txs_mean",
    "time_between_output_txs_median",
    "num_addr_transacted_multiple",
    "transacted_w_address_total",
    "transacted_w_address_min",
    "transacted_w_address_max",
    "transacted_w_address_mean",
    "transacted_w_address_median",
    "native_fee_rate_mean",
    "native_fee_units_total",
    "native_fee_units_mean",
    "gas_price_gwei_mean",
    "gas_used_mean",
    "bandwidth_used_total",
    "energy_used_total",
]

MISSING_INDICATOR_COLUMNS: list[str] = [
    "chain_fee_is_missing",
    "fee_ratio_is_missing",
    "native_fee_is_missing",
    "gas_price_is_missing",
    "gas_used_is_missing",
    "bandwidth_is_missing",
    "energy_is_missing",
]

# ── Engineered graph features (computed from AddrAddr_edgelist.csv during training) ──
GRAPH_FEATURE_COLUMNS: list[str] = [
    "illicit_neighbor_ratio_1hop",
    "illicit_neighbor_ratio_2hop",
    "shortest_path_to_known_illicit",
]

FEATURE_COLUMNS.extend(MISSING_INDICATOR_COLUMNS)
FEATURE_COLUMNS.extend(GRAPH_FEATURE_COLUMNS)

# ── GraphSAGE embedding columns (16 dims from the precomputed wallet embedding store) ──
GSAGE_EMBEDDING_COLUMNS: list[str] = [f"gsage_{dim}" for dim in range(16)]

# ── Entity-scale-relative features (promoted 92f config) ──
from app.ml.relative_features import (  # noqa: E402  (local import keeps constants co-located)
    RELATIVE_FEATURE_COLUMNS,
    load_relative_reference,
    relative_features_for_wallet,
)

# Width of the tabular+relative base vector (no embeddings).
TABULAR_REL_COLUMNS: list[str] = FEATURE_COLUMNS + RELATIVE_FEATURE_COLUMNS

# Full model input schema: 72 tabular/graph features + 16 GraphSAGE embedding dims
# + 4 entity-scale-relative features (the validated 92f promoted config).
MODEL_FEATURE_COLUMNS: list[str] = FEATURE_COLUMNS + GSAGE_EMBEDDING_COLUMNS + RELATIVE_FEATURE_COLUMNS


def assert_model_feature_schema(computed_columns: list[str]) -> None:
    """
    Guard for the 92-column model input (72 tabular + 16 embeddings + 4 relative).
    Raises AssertionError if the schemas don't match exactly.
    """
    assert computed_columns == MODEL_FEATURE_COLUMNS, (
        f"Model feature schema mismatch!\n"
        f"Expected: {MODEL_FEATURE_COLUMNS}\n"
        f"Got:      {computed_columns}"
    )


def add_embedding_columns(feature_vector: np.ndarray, embedding: np.ndarray) -> np.ndarray:
    """
    Concat a (n, 76) tabular+relative feature vector with a (n, 16) embedding
    into a (n, 92) model vector in the EXACT trained order.

    The deployed 92f artifact is fit on ``MODEL_FEATURE_COLUMNS`` =
    [tabular(72)][gsage(16)][relative(4)]. The vector passed in here is the
    [tabular(72)][relative(4)] base, so embeddings must be inserted BETWEEN
    tabular and relative — NOT appended at the end. Feeding the wrong order
    silently scrambles columns against the trained model.
    """
    vec = np.asarray(feature_vector, dtype=np.float32)
    emb = np.asarray(embedding, dtype=np.float32)
    if vec.ndim == 1:
        vec = vec.reshape(1, -1)
    if emb.ndim == 1:
        emb = emb.reshape(1, -1)
    assert vec.shape[1] == len(TABULAR_REL_COLUMNS), (
        f"tabular+relative vector width {vec.shape[1]} != TABULAR_REL_COLUMNS {len(TABULAR_REL_COLUMNS)}"
    )
    assert emb.shape[1] == len(GSAGE_EMBEDDING_COLUMNS), (
        f"embedding width {emb.shape[1]} != GSAGE dims {len(GSAGE_EMBEDDING_COLUMNS)}"
    )
    assert vec.shape[0] == emb.shape[0], "row count mismatch between tabular and embedding"
    assert len(MODEL_FEATURE_COLUMNS) == vec.shape[1] + emb.shape[1], (
        "tabular+relative+embedding width != MODEL_FEATURE_COLUMNS"
    )
    base = vec[:, : len(FEATURE_COLUMNS)]
    rel = vec[:, len(FEATURE_COLUMNS):]
    assert base.shape[1] == len(FEATURE_COLUMNS), "tabular base width mismatch"
    assert rel.shape[1] == len(RELATIVE_FEATURE_COLUMNS), "relative block width mismatch"
    return np.hstack([base, emb, rel])


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
    current_block: int = 860000,
) -> dict[str, float]:
    """
    Extract the 55 Elliptic++ feature schema features dynamically from a list of raw transactions.
    """
    sent_txs = [t for t in txs if t.from_address.lower() == address.lower()]
    recv_txs = [t for t in txs if t.to_address.lower() == address.lower()]
    # Sanitize and cap transaction amounts
    all_amounts = [min(1000000.0, max(0.0, float(t.amount))) for t in txs if 0 <= float(t.amount) < 1e15] if txs else [0.0]
    sent_amounts = [min(1000000.0, max(0.0, float(t.amount))) for t in sent_txs if 0 <= float(t.amount) < 1e15] if sent_txs else [0.0]
    recv_amounts = [min(1000000.0, max(0.0, float(t.amount))) for t in recv_txs if 0 <= float(t.amount) < 1e15] if recv_txs else [0.0]

    num_sent = float(len(sent_txs))
    num_recv = float(len(recv_txs))
    total_txs = float(len(txs))

    # Amounts statistics
    btc_transacted_total = float(sum(all_amounts))
    btc_transacted_min = float(min(all_amounts)) if all_amounts else 0.0
    btc_transacted_max = float(max(all_amounts)) if all_amounts else 0.0
    btc_transacted_mean = float(np.mean(all_amounts)) if all_amounts else 0.0
    btc_transacted_median = float(np.median(all_amounts)) if all_amounts else 0.0

    btc_sent_total = float(sum(sent_amounts))
    btc_sent_min = float(min(sent_amounts)) if sent_amounts else 0.0
    btc_sent_max = float(max(sent_amounts)) if sent_amounts else 0.0
    btc_sent_mean = float(np.mean(sent_amounts)) if sent_amounts else 0.0
    btc_sent_median = float(np.median(sent_amounts)) if sent_amounts else 0.0

    btc_received_total = float(sum(recv_amounts))
    btc_received_min = float(min(recv_amounts)) if recv_amounts else 0.0
    btc_received_max = float(max(recv_amounts)) if recv_amounts else 0.0
    btc_received_mean = float(np.mean(recv_amounts)) if recv_amounts else 0.0
    btc_received_median = float(np.median(recv_amounts)) if recv_amounts else 0.0

    # Dynamic block calculation (BTC Genesis: Jan 3 2009 1230950400, ~600s/block)
    GENESIS_TS = 1230950400.0

    def block_from_ts(ts: datetime) -> float:
        try:
            return max(0.0, float((ts.timestamp() - GENESIS_TS) / 600.0))
        except Exception:
            return float(current_block)

    if txs:
        all_blocks = [block_from_ts(t.timestamp) for t in txs]
        first_block = float(min(all_blocks))
        last_block = float(max(all_blocks))
        lifetime_in_blocks = max(0.0, float(last_block - first_block))
    else:
        first_block = float(current_block)
        last_block = float(current_block)
        lifetime_in_blocks = 0.0

    sent_blocks = [block_from_ts(t.timestamp) for t in sent_txs] if sent_txs else []
    recv_blocks = [block_from_ts(t.timestamp) for t in recv_txs] if recv_txs else []
    first_sent_block = float(min(sent_blocks)) if sent_blocks else 0.0
    first_received_block = float(min(recv_blocks)) if recv_blocks else 0.0

    # Dynamic consecutive transaction intervals (sorted chronologically)
    sorted_txs = sorted(txs, key=lambda t: t.timestamp)
    if len(sorted_txs) > 1:
        tx_diffs = [
            max(0.0, (sorted_txs[i + 1].timestamp - sorted_txs[i].timestamp).total_seconds() / 600.0)
            for i in range(len(sorted_txs) - 1)
        ]
        blocks_btwn_txs_total = float(sum(tx_diffs))
        blocks_btwn_txs_min = float(min(tx_diffs))
        blocks_btwn_txs_max = float(max(tx_diffs))
        blocks_btwn_txs_mean = float(np.mean(tx_diffs))
        blocks_btwn_txs_median = float(np.median(tx_diffs))
    else:
        blocks_btwn_txs_total = 0.0
        blocks_btwn_txs_min = 0.0
        blocks_btwn_txs_max = 0.0
        blocks_btwn_txs_mean = 0.0
        blocks_btwn_txs_median = 0.0

    sorted_sent = sorted(sent_txs, key=lambda t: t.timestamp)
    if len(sorted_sent) > 1:
        sent_diffs = [
            max(0.0, (sorted_sent[i + 1].timestamp - sorted_sent[i].timestamp).total_seconds() / 600.0)
            for i in range(len(sorted_sent) - 1)
        ]
        blocks_btwn_input_txs_total = float(sum(sent_diffs))
        blocks_btwn_input_txs_min = float(min(sent_diffs))
        blocks_btwn_input_txs_max = float(max(sent_diffs))
        blocks_btwn_input_txs_mean = float(np.mean(sent_diffs))
        blocks_btwn_input_txs_median = float(np.median(sent_diffs))
    else:
        blocks_btwn_input_txs_total = 0.0
        blocks_btwn_input_txs_min = 0.0
        blocks_btwn_input_txs_max = 0.0
        blocks_btwn_input_txs_mean = 0.0
        blocks_btwn_input_txs_median = 0.0

    sorted_recv = sorted(recv_txs, key=lambda t: t.timestamp)
    if len(sorted_recv) > 1:
        recv_diffs = [
            max(0.0, (sorted_recv[i + 1].timestamp - sorted_recv[i].timestamp).total_seconds() / 600.0)
            for i in range(len(sorted_recv) - 1)
        ]
        blocks_btwn_output_txs_total = float(sum(recv_diffs))
        blocks_btwn_output_txs_min = float(min(recv_diffs))
        blocks_btwn_output_txs_max = float(max(recv_diffs))
        blocks_btwn_output_txs_mean = float(np.mean(recv_diffs))
        blocks_btwn_output_txs_median = float(np.median(recv_diffs))
    else:
        blocks_btwn_output_txs_total = 0.0
        blocks_btwn_output_txs_min = 0.0
        blocks_btwn_output_txs_max = 0.0
        blocks_btwn_output_txs_mean = 0.0
        blocks_btwn_output_txs_median = 0.0

    # Counterparty addresses & frequencies
    counterparty_counts: dict[str, int] = {}
    for t in sent_txs:
        c_addr = t.to_address.lower()
        counterparty_counts[c_addr] = counterparty_counts.get(c_addr, 0) + 1
    for t in recv_txs:
        c_addr = t.from_address.lower()
        counterparty_counts[c_addr] = counterparty_counts.get(c_addr, 0) + 1

    unique_counterparties = float(len(counterparty_counts))
    counts_list = list(counterparty_counts.values()) if counterparty_counts else [0]
    num_addr_multiple = float(sum(1 for c in counts_list if c > 1))

    transacted_w_address_total = unique_counterparties
    transacted_w_address_min = float(min(counts_list)) if counterparty_counts else 0.0
    transacted_w_address_max = float(max(counts_list)) if counterparty_counts else 0.0
    transacted_w_address_mean = float(np.mean(counts_list)) if counterparty_counts else 0.0
    transacted_w_address_median = float(np.median(counts_list)) if counterparty_counts else 0.0

    native_fee_values = [float(t.fee_native) for t in txs if t.fee_native is not None and t.fee_native >= 0]
    gas_price_values = [float(t.gas_price_gwei) for t in txs if t.gas_price_gwei is not None and t.gas_price_gwei >= 0]
    gas_used_values = [float(t.gas_used) for t in txs if t.gas_used is not None and t.gas_used >= 0]
    bandwidth_values = [float(t.bandwidth_used) for t in txs if t.bandwidth_used is not None and t.bandwidth_used >= 0]
    energy_values = [float(t.energy_used) for t in txs if t.energy_used is not None and t.energy_used >= 0]

    # Use chain-native fee data when the explorer supplies it. BTC keeps the
    # legacy fee proxy only because the Elliptic++ training set has no fee field.
    if native_fee_values:
        fees_total = round(sum(native_fee_values), 6)
        fees_mean = round(float(np.mean(native_fee_values)), 6)
        fees_min = round(float(min(native_fee_values)), 6)
        fees_max = round(float(max(native_fee_values)), 6)
        fees_median = round(float(np.median(native_fee_values)), 6)
    else:
        fees_total = round(btc_transacted_total * 0.0001, 6)
        fees_mean = round(fees_total / max(1.0, total_txs), 6)
        fees_min = round(fees_mean * 0.5, 6)
        fees_max = round(fees_mean * 2.0, 6)
        fees_median = fees_mean

    has_native_fee = bool(native_fee_values)
    if chain.upper() == "BTC" or has_native_fee:
        fees_as_share = 0.0001
        fees_as_share_total = fees_as_share
        fees_as_share_min = fees_as_share * 0.5
        fees_as_share_max = fees_as_share * 2.0
        fees_as_share_mean = fees_as_share
        fees_as_share_median = fees_as_share
    else:
        fees_total = fees_min = fees_max = fees_mean = fees_median = float("nan")
        fees_as_share_total = fees_as_share_min = fees_as_share_max = fees_as_share_mean = fees_as_share_median = float("nan")

    timesteps_appeared = float(min(49.0, max(1.0, (lifetime_in_blocks / 2016.0) + 1.0)))

    feature_dict = {
        "num_txs_as_sender": num_sent,
        "num_txs_as_receiver": num_recv,
        "first_block_appeared_in": first_block,
        "last_block_appeared_in": last_block,
        "lifetime_in_blocks": lifetime_in_blocks,
        "total_txs": total_txs,
        "first_sent_block": first_sent_block,
        "first_received_block": first_received_block,
        "num_timesteps_appeared_in": timesteps_appeared,
        "value_transacted_total": btc_transacted_total,
        "value_transacted_min": btc_transacted_min,
        "value_transacted_max": btc_transacted_max,
        "value_transacted_mean": btc_transacted_mean,
        "value_transacted_median": btc_transacted_median,
        "value_sent_total": btc_sent_total,
        "value_sent_min": btc_sent_min,
        "value_sent_max": btc_sent_max,
        "value_sent_mean": btc_sent_mean,
        "value_sent_median": btc_sent_median,
        "value_received_total": btc_received_total,
        "value_received_min": btc_received_min,
        "value_received_max": btc_received_max,
        "value_received_mean": btc_received_mean,
        "value_received_median": btc_received_median,
        "chain_fee_total": fees_total,
        "chain_fee_min": fees_min,
        "chain_fee_max": fees_max,
        "chain_fee_mean": fees_mean,
        "chain_fee_median": fees_median,
        "fee_ratio_total": fees_as_share_total,
        "fee_ratio_min": fees_as_share_min,
        "fee_ratio_max": fees_as_share_max,
        "fee_ratio_mean": fees_as_share_mean,
        "fee_ratio_median": fees_as_share_median,
        "time_between_txs_total": blocks_btwn_txs_total,
        "time_between_txs_min": blocks_btwn_txs_min,
        "time_between_txs_max": blocks_btwn_txs_max,
        "time_between_txs_mean": blocks_btwn_txs_mean,
        "time_between_txs_median": blocks_btwn_txs_median,
        "time_between_input_txs_total": blocks_btwn_input_txs_total,
        "time_between_input_txs_min": blocks_btwn_input_txs_min,
        "time_between_input_txs_max": blocks_btwn_input_txs_max,
        "time_between_input_txs_mean": blocks_btwn_input_txs_mean,
        "time_between_input_txs_median": blocks_btwn_input_txs_median,
        "time_between_output_txs_total": blocks_btwn_output_txs_total,
        "time_between_output_txs_min": blocks_btwn_output_txs_min,
        "time_between_output_txs_max": blocks_btwn_output_txs_max,
        "time_between_output_txs_mean": blocks_btwn_output_txs_mean,
        "time_between_output_txs_median": blocks_btwn_output_txs_median,
        "num_addr_transacted_multiple": num_addr_multiple,
        "transacted_w_address_total": transacted_w_address_total,
        "transacted_w_address_min": transacted_w_address_min,
        "transacted_w_address_max": transacted_w_address_max,
        "transacted_w_address_mean": transacted_w_address_mean,
        "transacted_w_address_median": transacted_w_address_median,
        "native_fee_rate_mean": fees_mean,
        "native_fee_units_total": fees_total,
        "native_fee_units_mean": fees_mean,
        "gas_price_gwei_mean": float(np.mean(gas_price_values)) if gas_price_values else 0.0,
        "gas_used_mean": float(np.mean(gas_used_values)) if gas_used_values else 0.0,
        "bandwidth_used_total": float(sum(bandwidth_values)),
        "energy_used_total": float(sum(energy_values)),
    }

    feature_dict.update({
        "chain_fee_is_missing": float(not np.isfinite(feature_dict["chain_fee_total"])),
        "fee_ratio_is_missing": float(not np.isfinite(feature_dict["fee_ratio_total"])),
        "native_fee_is_missing": float(not native_fee_values),
        "gas_price_is_missing": float(not gas_price_values),
        "gas_used_is_missing": float(not gas_used_values),
        "bandwidth_is_missing": float(not bandwidth_values),
        "energy_is_missing": float(not energy_values),
    })

    return feature_dict


def compute_tabular_feature_vector(
    address: str,
    chain: str,
    txs: Optional[List[RawTx]] = None,
    graph_features: Optional[dict[str, float]] = None,
) -> np.ndarray:
    """
    Compute the (1, 76) tabular + relative-feature vector with strict schema
    validation. This is the base for the live path; embeddings are appended
    separately by ``compute_feature_vector`` / ``add_embedding_columns``.

    Args:
        graph_features: Optional dict with keys from GRAPH_FEATURE_COLUMNS.
            If None, all 3 graph features default to 0.0 (no graph signal).
    """
    raw_txs = txs or []
    feature_dict = extract_features_from_transactions(address, chain, raw_txs)

    for col in GRAPH_FEATURE_COLUMNS:
        feature_dict[col] = float(graph_features.get(col, 0.0)) if graph_features else 0.0

    computed_keys = list(feature_dict.keys())
    assert_feature_schema(computed_keys)

    base = [
        float(np.clip(np.nan_to_num(feature_dict[k], nan=0.0, posinf=1000000.0, neginf=0.0), -1e7, 1e7))
        for k in FEATURE_COLUMNS
    ]
    rel = relative_features_for_wallet(feature_dict, load_relative_reference())
    tab_rel = np.array(
        base + [rel[col] for col in RELATIVE_FEATURE_COLUMNS],
        dtype=np.float32,
    ).reshape(1, -1)
    assert tab_rel.shape[1] == len(TABULAR_REL_COLUMNS)
    return tab_rel


def compute_feature_vector(
    address: str,
    chain: str,
    txs: Optional[List[RawTx]] = None,
    graph_features: Optional[dict[str, float]] = None,
    embedding: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Compute the full (1, 92) model feature vector: 72 tabular/graph + 4 relative
    + 16 GraphSAGE embeddings, with strict schema validation.

    Args:
        graph_features: Optional dict with keys from GRAPH_FEATURE_COLUMNS.
            If None, all 3 graph features default to 0.0 (no graph signal).
        embedding: Optional (16,) embedding row. When None, a synchronous
            lookup from the wallet embedding store is used (zero fallback for
            fresh/unseen addresses), mirroring production behavior.
    """
    tab_rel = compute_tabular_feature_vector(address, chain, txs, graph_features=graph_features)
    if embedding is None:
        from app.ml.embedding_store import lookup_embedding

        embedding = lookup_embedding(address)
    return add_embedding_columns(tab_rel, embedding)
