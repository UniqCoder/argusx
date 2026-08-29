"""
app/tests/test_risk.py — Test suite for ML Risk Scoring, SHAP explanations, and Registry Refresh (Phase 4).
"""
import pytest
from httpx import AsyncClient
import numpy as np

from app.ml.explain import explain_wallet_risk
from app.ml.features import FEATURE_COLUMNS, assert_feature_schema, compute_feature_vector
from app.ml.model import map_score_to_tier, predict_risk_score
from app.schemas.common import EvidenceDirection, RiskTier
from app.services import registry_service


def test_feature_schema_assertion_guard():
    """Verify that the feature schema assertion strictly guards column names and order."""
    # Exact match passes
    assert_feature_schema(list(FEATURE_COLUMNS))

    # Missing column fails
    with pytest.raises(AssertionError):
        assert_feature_schema(list(FEATURE_COLUMNS[:-1]))

    # Scrambled order fails
    with pytest.raises(AssertionError):
        assert_feature_schema(list(reversed(FEATURE_COLUMNS)))

    # Extra column fails
    with pytest.raises(AssertionError):
        assert_feature_schema(list(FEATURE_COLUMNS) + ["extra_unaligned_feature"])


def test_risk_model_prediction_and_tier_mapping():
    """Verify model output shape and tier assignment."""
    vec = np.zeros((1, 55), dtype=np.float32)
    score = predict_risk_score(vec)
    assert 0.0 <= score <= 1.0

    # Tier mapping tests
    assert map_score_to_tier(0.95) == RiskTier.critical
    assert map_score_to_tier(0.75) == RiskTier.high
    assert map_score_to_tier(0.45) == RiskTier.medium
    assert map_score_to_tier(0.15) == RiskTier.low


def test_shap_explainability_evidence_generation():
    """Verify SHAP explanation produces evidence matching openapi.yaml."""
    vec = np.ones((1, 55), dtype=np.float32) * 5.0
    evidence = explain_wallet_risk(vec, top_k=5)

    assert isinstance(evidence, list)
    assert len(evidence) <= 5
    for item in evidence:
        assert item.feature_name in FEATURE_COLUMNS
        assert item.contribution >= 0.0
        assert item.direction in (EvidenceDirection.increases_risk, EvidenceDirection.decreases_risk)


@pytest.mark.asyncio
async def test_get_wallet_risk_endpoint_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/wallets/bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh/risk?chain=BTC")
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_get_wallet_risk_endpoint_invalid_chain(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/wallets/bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh/risk?chain=INVALID_CHAIN",
        headers=auth_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_get_wallet_risk_endpoint_success(client: AsyncClient, auth_headers: dict):
    addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    response = await client.get(
        f"/api/v1/wallets/{addr}/risk?chain=BTC",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "risk_score" in data
    assert 0.0 <= data["risk_score"] <= 1.0
    assert "risk_tier" in data
    assert data["risk_tier"] in [t.value for t in RiskTier]
    assert "evidence" in data
    assert isinstance(data["evidence"], list)


@pytest.mark.asyncio
async def test_registry_refresh_end_to_end_integration(
    client: AsyncClient,
    fake_redis,
    vasp_api_headers: dict,
):
    """
    Verify that registry_service updates Redis, which immediately affects /check-wallet.
    """
    addr = "1TestHighRiskAddress9999"
    chain = "BTC"

    # Pre-condition: Unflagged address gives "allow"
    res1 = await client.post(
        "/check-wallet",
        json={"chain": chain, "address": addr, "amount": 1.5, "vasp_id": "VASP_TEST"},
        headers=vasp_api_headers,
    )
    assert res1.status_code == 200
    assert res1.json()["action"] == "allow"

    # Set critical risk entry in Redis registry
    await registry_service.set_risk_entry(
        redis_client=fake_redis,
        chain=chain,
        address=addr,
        score=0.92,
        tier=RiskTier.critical,
        case_ref="CR-2026-001",
    )

    # Post-condition: Same address now instantly triggers "block" in /check-wallet
    res2 = await client.post(
        "/check-wallet",
        json={"chain": chain, "address": addr, "amount": 1.5, "vasp_id": "VASP_TEST"},
        headers=vasp_api_headers,
    )
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["action"] == "block"
    assert data2["risk_score"] == 0.92
    assert data2["case_ref"] == "CR-2026-001"
