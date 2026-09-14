"""
app/ml/model.py — Risk Model inference and tier mapping.

Loads the serialized model and outputs probability scores and RiskTier enums.
"""
import hashlib
import os
from typing import Optional
import joblib
import numpy as np

from app.schemas.common import RiskTier

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
MODEL_PATH = os.path.join(ARTIFACTS_DIR, "risk_model.joblib")

_model_instance = None
_model_version: Optional[str] = None


def clear_model_cache():
    """Clear cached model instance."""
    global _model_instance, _model_version
    _model_instance = None
    _model_version = None


def get_model():
    """Lazy load singleton XGBoost model instance."""
    global _model_instance, _model_version
    if _model_instance is None:
        if os.path.exists(MODEL_PATH):
            _model_instance = joblib.load(MODEL_PATH)
        else:
            # Train from the processed splits + embedding store if artifact is missing
            from app.ml.train import train_combined_model
            train_combined_model()
            _model_instance = joblib.load(MODEL_PATH)
        # Content-addressed, not a manually-bumped string that can be
        # forgotten: a version that changes if and only if the artifact
        # bytes on disk actually changed (retrain, promotion, rollback).
        # Two replicas that happened to load/train different artifacts
        # (see the fallback branch above) now surface that divergence
        # instead of scoring silently differently with no way to tell why.
        with open(MODEL_PATH, "rb") as f:
            _model_version = hashlib.sha256(f.read()).hexdigest()[:12]
    return _model_instance


def get_model_version() -> str:
    """Short content hash of the currently-loaded model artifact.

    Deterministic for the life of this process: calling it before any
    inference forces the same lazy-load `get_model()` would do, so the
    version reported always matches the model actually used for scoring.
    """
    if _model_instance is None:
        get_model()
    return _model_version or "unknown"


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
