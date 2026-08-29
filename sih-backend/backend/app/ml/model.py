"""
app/ml/model.py — Risk Model inference and tier mapping.

Loads the serialized model and outputs probability scores and RiskTier enums.
"""
import os
from typing import Optional
import joblib
import numpy as np

from app.schemas.common import RiskTier

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "risk_model.joblib")

_model_instance = None


def get_model():
    """Lazy load singleton XGBoost model instance."""
    global _model_instance
    if _model_instance is None:
        if os.path.exists(MODEL_PATH):
            _model_instance = joblib.load(MODEL_PATH)
        else:
            # Fallback for initial tests / cold environment
            from app.ml.train import generate_synthetic_elliptic_dataset, train_elliptic_model
            df_f, df_c = generate_synthetic_elliptic_dataset(n_samples=2000)
            train_elliptic_model(df_f, df_c)
            _model_instance = joblib.load(MODEL_PATH)
    return _model_instance


def predict_risk_score(feature_vector: np.ndarray) -> float:
    """
    Predict probability of wallet being illicit.
    Returns float in range [0.0, 1.0].
    """
    model = get_model()
    proba = model.predict_proba(feature_vector)[0, 1]
    return float(np.clip(proba, 0.0, 1.0))


def map_score_to_tier(score: float) -> RiskTier:
    """
    Map risk probability score to closed RiskTier enum (contracts/entities.md).
    - >= 0.85 -> critical
    - >= 0.60 -> high
    - >= 0.30 -> medium
    - else -> low
    """
    if score >= 0.85:
        return RiskTier.critical
    if score >= 0.60:
        return RiskTier.high
    if score >= 0.30:
        return RiskTier.medium
    return RiskTier.low
