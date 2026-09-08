"""
app/ml/live_ood_diagnostic.py — Offline proxy for the Task 1 live /risk diagnostic.

Scores the two known high-profile false-positive addresses (Satoshi Genesis,
Ethereum Foundation) through:
  (a) the production 88-feature artifact (risk_model.joblib), and
  (b) the Task-1 92-feature variant (additive entity-scale-relative features),
using the SAME live /risk feature-extraction path (compute_feature_vector +
zero-embedding fallback, since neither address is a node in the Elliptic++
graph).

The transaction streams are REPRODUCIBLE curated profiles matching the documented
live scoring runs (docs/ml.md: Satoshi ~era-block age, low tx count, fee_ratio
0.0002; ETH Foundation similar age, higher tx count). This is a directional
diagnostic only — the promotion gate remains the offline BTC AUC-PR / recall
comparison.
"""
from __future__ import annotations

import logging
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from app.ml.features import (
    FEATURE_COLUMNS,
    GSAGE_EMBEDDING_COLUMNS,
    MODEL_FEATURE_COLUMNS,
    add_embedding_columns,
    compute_feature_vector,
    compute_tabular_feature_vector,
)
from app.ml.model import get_model, map_score_to_tier
from app.ml.promotion_experiments import (
    add_relative_features,
    load_splits,
    run_relative_feature_experiment,
)
from app.schemas.common import Chain
from app.services.explorers.base import RawTx

logger = logging.getLogger(__name__)


def satoshi_profile() -> list[RawTx]:
    """Satoshi Genesis-like: earliest era, tiny tx count, low fee_ratio."""
    base_ts = datetime(2017, 1, 3, tzinfo=timezone.utc)
    txs = [
        RawTx(
            tx_hash="satoshi_0",
            from_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            to_address="1Counterparty0000000000000000000000000",
            amount=50.0,
            chain=Chain.BTC,
            timestamp=base_ts,
        )
    ]
    for i in range(1, 6):
        txs.append(RawTx(
            tx_hash=f"satoshi_{i}",
            from_address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            to_address=f"1Counterparty{i:09d}",
            amount=0.5,
            chain=Chain.BTC,
            timestamp=base_ts + timedelta(days=i * 300),
        ))
    return txs


def eth_foundation_profile() -> list[RawTx]:
    """ETH Foundation-like: same era, higher tx count, native ETH fees."""
    base_ts = datetime(2017, 6, 1, tzinfo=timezone.utc)
    return [
        RawTx(
            tx_hash=f"ef_{i}",
            from_address="0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe",
            to_address=f"0xRecv{i:08x}",
            amount=2.5,
            chain=Chain.ETH,
            timestamp=base_ts + timedelta(days=i * 40),
            fee_native=0.002,
            gas_price_gwei=20.0,
            gas_used=50000.0,
        )
        for i in range(20)
    ]


def score_variant(model, feature_vector: np.ndarray) -> tuple[float, str]:
    score = float(model.predict_proba(feature_vector)[0, 1])
    return round(score, 4), map_score_to_tier(score).value


def main() -> dict:
    logging.basicConfig(level=logging.WARNING)

    prod_model = get_model()
    task1 = run_relative_feature_experiment(*load_splits())
    rel_model = task1["clf"]

    report = {"note": "directional diagnostic; promotion gate = offline BTC metrics"}
    for label, chain, txs in [
        ("satoshi_genesis", Chain.BTC, satoshi_profile()),
        ("eth_foundation", Chain.ETH, eth_foundation_profile()),
    ]:
        base_vec = compute_tabular_feature_vector("addr", chain.value, txs)  # 76 cols (tab+relative)
        emb = np.zeros((len(GSAGE_EMBEDDING_COLUMNS),), dtype=np.float32)
        # add_embedding_columns assembles [tabular(72)][gsage(16)][relative(4)],
        # EXACTLY matching MODEL_FEATURE_COLUMNS and the deployed artifact.
        model_vec = add_embedding_columns(base_vec, emb)
        assert model_vec.shape[1] == len(MODEL_FEATURE_COLUMNS)
        emb_block = model_vec[0, len(FEATURE_COLUMNS) : len(FEATURE_COLUMNS) + len(GSAGE_EMBEDDING_COLUMNS)]
        assert np.array_equal(emb_block, emb), "embedding slots misordered — check add_embedding_columns"

        prod_score, prod_tier = score_variant(prod_model, model_vec)
        rel_score, rel_tier = score_variant(rel_model, model_vec)

        report[label] = {
            "production_92f_score": prod_score,
            "production_92f_tier": prod_tier,
            "task1_92f_retrained_score": rel_score,
            "task1_92f_retrained_tier": rel_tier,
            "delta": round(rel_score - prod_score, 4),
            "raw_92_vector": [round(float(v), 4) for v in model_vec[0]],
        }
        print(f"[{label}] 92f(prod)={prod_score:.4f} ({prod_tier})  ->  92f(retrained)={rel_score:.4f} ({rel_tier})  delta={rel_score - prod_score:+.4f}")
    out = os.path.join(os.path.dirname(__file__), "artifacts", "live_ood_diagnostic.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    return report


if __name__ == "__main__":
    main()