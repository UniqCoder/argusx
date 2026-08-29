"""
app/ml/risk_model.py — XGBoost/LightGBM risk scoring model (Phase 4).

Training: Elliptic++ Actors Dataset, temporal split (~34/15 time steps).
Metric priority: AUC-PR → precision/recall at threshold → FPR (<1%) → AUC-ROC → calibration.
Phase 0: stub only.
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).parent / "artifacts" / "risk_model.pkl"


def load_model():
    """Phase 4: load trained XGBoost/LightGBM model from disk."""
    raise NotImplementedError("Risk model loading implemented in Phase 4.")


async def predict(feature_vector) -> tuple[float, list[dict]]:
    """
    Phase 4: predict risk score + SHAP evidence for a wallet.
    Returns (risk_score: float, evidence: list[RiskEvidence dicts]).
    """
    raise NotImplementedError("Risk prediction implemented in Phase 4.")
