"""
app/tests/test_risk.py — Test suite for ML Risk Scoring, SHAP explanations, and Registry Refresh (Phase 4).
"""
import pytest
from httpx import AsyncClient
import numpy as np
from datetime import datetime, timezone

from app.ml.explain import explain_wallet_risk
from app.ml.features import FEATURE_COLUMNS, GSAGE_EMBEDDING_COLUMNS, MODEL_FEATURE_COLUMNS, RELATIVE_FEATURE_COLUMNS, add_embedding_columns, assert_feature_schema, assert_model_feature_schema, compute_feature_vector
from app.ml.model import map_score_to_tier, predict_risk_score
from app.schemas.common import EvidenceDirection, RiskTier
from app.services import registry_service, sanctions_service
from app.services.explorers.base import RawTx


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


def test_receiver_name_and_native_chain_features_are_present():
    tx = RawTx(
        tx_hash="0x1",
        from_address="0xsender",
        to_address="0xreceiver",
        amount=1.0,
        chain="ETH",
        timestamp=datetime.now(timezone.utc),
        fee_native=0.002,
        gas_price_gwei=20.0,
        gas_used=100000.0,
    )
    vector = compute_feature_vector("0xreceiver", "ETH", [tx])
    assert vector.shape == (1, len(MODEL_FEATURE_COLUMNS))
    assert "num_txs_as_receiver" in FEATURE_COLUMNS
    assert "num_txs_as receiver" not in FEATURE_COLUMNS
    assert vector[0, FEATURE_COLUMNS.index("gas_price_gwei_mean")] == 20.0
    assert vector[0, FEATURE_COLUMNS.index("gas_used_mean")] == 100000.0

    assert vector[0, FEATURE_COLUMNS.index("illicit_neighbor_ratio_1hop")] == 0.0
    assert vector[0, FEATURE_COLUMNS.index("illicit_neighbor_ratio_2hop")] == 0.0
    assert vector[0, FEATURE_COLUMNS.index("shortest_path_to_known_illicit")] == 0.0


def test_compute_feature_vector_shape_both_chains():
    """Verify compute_feature_vector produces the full 92-feature vector for BTC and ETH."""
    btc_tx = RawTx(
        tx_hash="0xabc",
        from_address="1sender",
        to_address="1receiver",
        amount=0.5,
        chain="BTC",
        timestamp=datetime.now(timezone.utc),
    )
    btc_vec = compute_feature_vector("1receiver", "BTC", [btc_tx])
    assert btc_vec.shape == (1, 92), (
        f"BTC vector shape {btc_vec.shape} != expected (1, 92)"
    )
    assert btc_vec.shape == (1, len(MODEL_FEATURE_COLUMNS))

    eth_tx = RawTx(
        tx_hash="0xdef",
        from_address="0xsender",
        to_address="0xreceiver",
        amount=1.0,
        chain="ETH",
        timestamp=datetime.now(timezone.utc),
        fee_native=0.002,
        gas_price_gwei=20.0,
        gas_used=100000.0,
    )
    eth_vec = compute_feature_vector("0xreceiver", "ETH", [eth_tx])
    assert eth_vec.shape == (1, 92), (
        f"ETH vector shape {eth_vec.shape} != expected (1, 92)"
    )
    assert eth_vec.shape == (1, len(MODEL_FEATURE_COLUMNS))

    assert not np.all(np.isnan(btc_vec)), "BTC vector has all-NaN columns"
    assert not np.all(np.isnan(eth_vec)), "ETH vector has all-NaN columns"


def test_compute_feature_vector_with_graph_features():
    """Verify graph_features parameter injects values correctly."""
    graph_feats = {
        "illicit_neighbor_ratio_1hop": 0.35,
        "illicit_neighbor_ratio_2hop": 0.12,
        "shortest_path_to_known_illicit": 2,
    }
    vec = compute_feature_vector("0xaddr", "ETH", [], graph_features=graph_feats)
    assert vec.shape == (1, 92)
    # float32 storage: compare approximately
    assert vec[0, FEATURE_COLUMNS.index("illicit_neighbor_ratio_1hop")] == pytest.approx(0.35, abs=1e-6)
    assert vec[0, FEATURE_COLUMNS.index("illicit_neighbor_ratio_2hop")] == pytest.approx(0.12, abs=1e-6)
    assert vec[0, FEATURE_COLUMNS.index("shortest_path_to_known_illicit")] == pytest.approx(2.0, abs=1e-6)


def test_model_feature_schema_and_embedding_augmentation():
    """Verify the 92-column model schema and embedding augmentation helper."""
    assert len(MODEL_FEATURE_COLUMNS) == 92
    assert_model_feature_schema(list(MODEL_FEATURE_COLUMNS))
    # 76-tabular+relative vector + 16-zero embedding -> 92
    tab_rel = np.zeros((1, len(FEATURE_COLUMNS) + 4), dtype=np.float32)
    emb = np.zeros((len(GSAGE_EMBEDDING_COLUMNS),), dtype=np.float32)
    model_vec = add_embedding_columns(tab_rel, emb)
    assert model_vec.shape == (1, 92), (
        f"model vector shape {model_vec.shape} != (1, 92)"
    )
    assert model_vec.shape == (1, len(MODEL_FEATURE_COLUMNS)), (
        f"model vector shape {model_vec.shape} != (1, {len(MODEL_FEATURE_COLUMNS)})"
    )
    with pytest.raises(AssertionError):
        add_embedding_columns(np.zeros((1, len(FEATURE_COLUMNS) - 1), dtype=np.float32), emb)


def test_add_embedding_columns_order_matches_model_schema():
    """Regression guard: embeddings must sit in [tabular, tabular+16) with
    relative features last, exactly matching MODEL_FEATURE_COLUMNS and the
    trained 92f artifact. A prior bug concatenated [tabular][relative][gsage],
    silently scrambling every live vector against the deployed model."""
    tab_rel = np.zeros((1, len(FEATURE_COLUMNS) + 4), dtype=np.float32)
    emb = np.arange(1, 17, dtype=np.float32)
    model_vec = add_embedding_columns(tab_rel, emb)
    assert model_vec.shape == (1, len(MODEL_FEATURE_COLUMNS)) == (1, 92)

    n_tab = len(FEATURE_COLUMNS)
    emb_slot = model_vec[0, n_tab : n_tab + len(GSAGE_EMBEDDING_COLUMNS)]
    assert np.array_equal(emb_slot, emb), "embedding not in [tabular, tabular+16) slots"

    rel_slot = model_vec[0, n_tab + len(GSAGE_EMBEDDING_COLUMNS):]
    assert rel_slot.shape == (len(RELATIVE_FEATURE_COLUMNS),)
    assert np.all(rel_slot == 0.0)


def test_risk_model_prediction_and_tier_mapping():
    """Verify model output shape and tier assignment."""
    vec = np.zeros((1, len(MODEL_FEATURE_COLUMNS)), dtype=np.float32)
    score = predict_risk_score(vec)
    assert 0.0 <= score <= 1.0

    # Tier mapping tests
    assert map_score_to_tier(0.95) == RiskTier.critical
    assert map_score_to_tier(0.75) == RiskTier.high
    assert map_score_to_tier(0.45) == RiskTier.medium
    assert map_score_to_tier(0.15) == RiskTier.low


def test_shap_explainability_evidence_generation():
    """Verify SHAP explanation produces evidence matching openapi.yaml."""
    vec = np.ones((1, len(MODEL_FEATURE_COLUMNS)), dtype=np.float32) * 5.0
    evidence = explain_wallet_risk(vec, top_k=5)

    assert isinstance(evidence, list)
    assert len(evidence) <= 5
    for item in evidence:
        assert item.feature_name in MODEL_FEATURE_COLUMNS
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


# ── Sanctions interception (USP 2) ───────────────────────────────────────────

def test_sanctions_seed_lookup_contract():
    """Curated OFAC seed resolves to its designations; unflagged addresses miss.

    Mirrors the slot-layout regression guard: pins the committed seed (133
    addresses, three designations) so a future rebuild cannot silently drop
    or re-tag a sanctioned designation.
    """
    assert sanctions_service.curated_address_count() == 133

    gar = sanctions_service.lookup_sanctioned("BTC", "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1")
    assert gar is not None
    assert gar["designation"] == "Garantex Europe OU"
    assert gar["ofac_list"] == "SDN"
    assert "RUSSIA-EO14024" in gar["programs"] and "CYBER4" in gar["programs"]

    gar_eth = sanctions_service.lookup_sanctioned("ETH", "0xD8500C631dC32FA18645B7436344a99E4825e10e")
    assert gar_eth is not None and gar_eth["designation"] == "Garantex Europe OU"

    hydra = sanctions_service.lookup_sanctioned("BTC", "3K4rjdh8A5yi6LWvft2rbmyZvqEbPSSSX4")
    assert hydra is not None and hydra["designation"] == "Hydra Market"

    semenov = sanctions_service.lookup_sanctioned("ETH", "0xdcbEfFBECcE100cCE9E4b153C4e15cB885643193")
    assert semenov is not None
    assert semenov["designation"] == "Semenov Roman (Tornado Cash co-founder)"

    assert sanctions_service.lookup_sanctioned("BTC", "1FfmbHfnpaZjKFvyi1okTjJJusN455paPH") is None
    assert sanctions_service.lookup_sanctioned("TRON", "TNVDQgkxzyUhGWMcbC6wRocPGxLL5SxkSd") is None


@pytest.mark.asyncio
async def test_sanctions_override_hard_blocks_before_ml(monkeypatch, client: AsyncClient, auth_headers: dict):
    """A curated sanctioned address is critical / score 1.0 even if ML blows up.

    The interception must run before model inference: if the model path is ever
    reached for a sanctioned address, this test fails loudly.
    """
    from app.services import risk_service as risk_service_module

    def _ml_must_not_run(*args, **kwargs):
        raise AssertionError("ML inference must not run for a sanctioned address")

    monkeypatch.setattr(risk_service_module, "predict_risk_score", _ml_must_not_run)

    addr = "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1"
    resp = await client.get(f"/api/v1/wallets/{addr}/risk?chain=BTC", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_score"] == 1.0
    assert data["risk_tier"] == RiskTier.critical.value
    assert data["risk_source"] == "sanctions_override"
    ev = data["evidence"][0]
    assert ev["feature_name"] == "sanctions_interception"
    assert "Garantex Europe OU" in ev["detail"]
    assert "SDN" in ev["detail"]


@pytest.mark.asyncio
async def test_sanctions_check_wallet_hot_path_blocks_seeded(
    client: AsyncClient,
    fake_redis,
    vasp_api_headers: dict,
):
    """Seeded sanctioned addresses force 'block' on the /check-wallet hot path."""
    await sanctions_service.seed_redis(redis_client=fake_redis)

    addr = "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1"
    resp = await client.post(
        "/check-wallet",
        json={"chain": "BTC", "address": addr, "amount": 1.5},
        headers=vasp_api_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "block"
    assert data["risk_score"] == 1.0
