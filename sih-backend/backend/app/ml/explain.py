"""
app/ml/explain.py — SHAP Explainability Engine for Wallet Risk Scoring (Phase 4).

Generates evidence arrays for risk explanations matching contracts/openapi.yaml:
  - feature_name: str
  - contribution: float
  - direction: "increases_risk" | "decreases_risk"
"""
import structlog
from typing import List
import numpy as np
import shap

from app.ml.features import MODEL_FEATURE_COLUMNS
from app.ml.model import get_model
from app.schemas.common import EvidenceDirection
from app.schemas.wallet import RiskEvidence

logger = structlog.get_logger(__name__)

_explainer_instance = None


def clear_explainer_cache():
    """Clear cached TreeExplainer instance."""
    global _explainer_instance
    _explainer_instance = None


def get_explainer():
    """Singleton SHAP TreeExplainer instance."""
    global _explainer_instance
    if _explainer_instance is None:
        model = get_model()
        _explainer_instance = shap.TreeExplainer(model)
    return _explainer_instance


def explain_wallet_risk(feature_vector: np.ndarray, top_k: int = 5) -> List[RiskEvidence]:
    """
    Compute SHAP values for a feature vector and extract top driving features.
    """
    explainer = get_explainer()
    shap_values = explainer.shap_values(feature_vector)

    if isinstance(shap_values, list):
        # Multi-class output, take positive class
        vals = shap_values[1][0]
    elif len(shap_values.shape) == 2:
        vals = shap_values[0]
    else:
        vals = shap_values

    # Pair features with their SHAP impact
    feature_names = [MODEL_FEATURE_COLUMNS[i] for i in range(len(vals))]
    # Group 2 (gated): raw full SHAP vector — DEBUG only.
    logger.debug(
        "shap_values_full",
        shap_values=list(zip(feature_names, [float(v) for v in vals])),
    )
    evidence_list = []
    for col, val in zip(feature_names, vals):
        contrib = float(val)
        if abs(contrib) < 1e-4:
            continue
        direction = EvidenceDirection.increases_risk if contrib > 0 else EvidenceDirection.decreases_risk
        evidence_list.append(
            RiskEvidence(
                feature_name=col,
                contribution=round(abs(contrib), 4),
                direction=direction,
            )
        )

    # Sort by contribution magnitude descending
    evidence_list.sort(key=lambda x: x.contribution, reverse=True)

    # If no non-zero SHAP values (e.g. zero transaction activity), supply standard baseline evidence
    if not evidence_list:
        # Group 1 (permanent): surface the static-placeholder branch explicitly so
        # "SHAP ~= 0 → deterministic evidence" is observable rather than assumed.
        logger.info("shap_static_placeholder_used", non_zero_shap_evidence=0)
        evidence_list = [
            RiskEvidence(
                feature_name="lifetime_in_blocks",
                contribution=0.01,
                direction=EvidenceDirection.decreases_risk,
            ),
            RiskEvidence(
                feature_name="btc_transacted_total",
                contribution=0.01,
                direction=EvidenceDirection.decreases_risk,
            ),
        ]

    return evidence_list[:top_k]
