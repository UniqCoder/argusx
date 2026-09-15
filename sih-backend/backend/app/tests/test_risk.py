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
async def test_sanctions_override_falls_back_cleanly_if_ml_fails(
    monkeypatch, client: AsyncClient, auth_headers: dict
):
    """A curated sanctioned address stays critical even if ML inference blows up.

    Sanctions are looked up first but no longer short-circuit the ML pipeline
    (a flat score=1.0 on every match discarded real computed behavior — see
    test_sanctions_blends_with_real_ml_score below for the normal path). If
    ML inference itself fails, the response degrades to the sanctions-only
    floor rather than 500ing or losing the sanctions signal.
    """
    from app.services import risk_service as risk_service_module

    def _ml_blows_up(*args, **kwargs):
        raise RuntimeError("simulated model failure")

    monkeypatch.setattr(risk_service_module, "predict_risk_score", _ml_blows_up)

    addr = "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1"
    resp = await client.get(f"/api/v1/wallets/{addr}/risk?chain=BTC", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_score"] == sanctions_service.SANCTIONS_SCORE_FLOOR
    assert data["risk_tier"] == RiskTier.critical.value
    assert data["risk_source"] == "sanctions_override"
    ev = data["evidence"][0]
    assert ev["feature_name"] == "sanctions_interception"
    assert "Garantex Europe OU" in ev["detail"]
    assert "SDN" in ev["detail"]


@pytest.mark.asyncio
async def test_sanctions_blends_with_real_ml_score(client: AsyncClient, auth_headers: dict):
    """The normal path: ML still runs for a sanctioned address, and the final
    score is max(ml_score, floor) — real behavioral evidence blended with the
    sanctions floor, not a bare hardcoded 1.0 with no computation behind it.
    """
    addr = "3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1"
    resp = await client.get(f"/api/v1/wallets/{addr}/risk?chain=BTC", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_score"] >= sanctions_service.SANCTIONS_SCORE_FLOOR
    assert data["risk_tier"] == RiskTier.critical.value
    assert data["risk_source"] == "sanctions_blended"
    feature_names = [e["feature_name"] for e in data["evidence"]]
    assert "sanctions_interception" in feature_names
    # Real ML factors are still present alongside the sanctions evidence —
    # the point of blending instead of overriding.
    assert len(feature_names) > 1


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
    assert data["risk_score"] == sanctions_service.SANCTIONS_SCORE_FLOOR


# ── Determinism & cross-endpoint consistency (risk-score pipeline audit) ────
#
# Every test below drives the REAL feature-extraction -> model -> SHAP
# pipeline (evaluate_wallet_risk itself is never mocked) but replaces the
# three network-dependent inputs — the block explorer, live Neo4j graph
# features, and the embedding store — with fixed, in-memory values. That
# isolates "does this pipeline behave deterministically" from "is Etherscan
# reachable right now", which is a real and separate question these tests
# are not trying to answer.

DETERMINISTIC_WALLET = "1DeterministicWallet"


def _fixed_btc_txs() -> list[RawTx]:
    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        RawTx(tx_hash="detTx1", from_address="1SenderAAA", to_address=DETERMINISTIC_WALLET,
              amount=0.5, chain="BTC", timestamp=ts, asset="BTC"),
        RawTx(tx_hash="detTx2", from_address=DETERMINISTIC_WALLET, to_address="1ReceiverBBB",
              amount=0.3, chain="BTC", timestamp=ts, asset="BTC"),
    ]


async def _fake_graph_features(address, chain, timeout_seconds=2.0):
    return {}, "empty"


async def _fake_embeddings(address, chain, timeout_seconds=2.0):
    return np.zeros(len(GSAGE_EMBEDDING_COLUMNS), dtype=np.float32), "fallback"


def _patch_deterministic_pipeline(monkeypatch, txs: list[RawTx] | None = None):
    """Isolate evaluate_wallet_risk from live explorers/Neo4j/embeddings so
    a test exercises the real scoring pipeline deterministically, with no
    network dependency. Patches the SOURCE modules risk_service.py imports
    from at call time (`from X import Y` inside the function body re-reads
    the current attribute on X every call), not risk_service's own module.
    """
    import app.ml.embedding_store as embedding_store_module
    import app.ml.live_graph_features as live_graph_features_module
    from app.services import risk_service as risk_service_module

    txs = txs if txs is not None else _fixed_btc_txs()

    async def _fake_get_transactions(address, limit=25):
        return list(txs)

    monkeypatch.setattr(risk_service_module.btc_explorer, "get_transactions", _fake_get_transactions)
    monkeypatch.setattr(
        live_graph_features_module, "compute_live_graph_features_with_fallback", _fake_graph_features
    )
    monkeypatch.setattr(embedding_store_module, "get_live_embeddings", _fake_embeddings)


@pytest.mark.asyncio
async def test_same_snapshot_same_score_repeated_runs(monkeypatch, db_session):
    """Same wallet + same evidence snapshot = exactly the same result, run
    after run after run — score, tier, snapshot_id, model/schema version,
    and the SHAP evidence list itself, all byte-identical."""
    from app.schemas.common import Chain
    from app.services.risk_service import evaluate_wallet_risk

    _patch_deterministic_pipeline(monkeypatch)

    r1 = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)
    r2 = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)
    r3 = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)

    assert r1.risk_score == r2.risk_score == r3.risk_score
    assert r1.risk_tier == r2.risk_tier == r3.risk_tier
    assert r1.snapshot_id == r2.snapshot_id == r3.snapshot_id
    assert r1.model_version == r2.model_version == r3.model_version
    assert r1.feature_schema_version == r2.feature_schema_version == r3.feature_schema_version
    assert [(e.feature_name, e.contribution, e.direction) for e in r1.evidence] == \
           [(e.feature_name, e.contribution, e.direction) for e in r2.evidence]


@pytest.mark.asyncio
async def test_same_wallet_identical_across_risk_and_deposit_watch_endpoints(
    monkeypatch, client: AsyncClient, fake_redis, auth_headers: dict, vasp_api_headers: dict,
):
    """The SAME wallet returns the EXACT same score from GET /risk (Risk
    Intelligence / Investigation / Cases / Reports all read this) and from
    POST /check-wallet (Deposit Watch's hot path) — because the hot path
    reads the registry entry risk_service.py's write-through just wrote,
    not a second, independent computation."""
    from app.services import registry_service as registry_service_module

    _patch_deterministic_pipeline(monkeypatch)
    # /check-wallet's Redis dependency is overridden to `fake_redis` by the
    # `client` fixture; route risk_service's write-through through the same
    # store so this test proves the real wiring, not two separate Redises.
    monkeypatch.setattr(registry_service_module, "get_redis_client", lambda: fake_redis)

    resp = await client.get(
        f"/api/v1/wallets/{DETERMINISTIC_WALLET}/risk?chain=BTC", headers=auth_headers
    )
    assert resp.status_code == 200
    risk_data = resp.json()

    dw = await client.post(
        "/check-wallet",
        json={"chain": "BTC", "address": DETERMINISTIC_WALLET, "amount": 1.0},
        headers=vasp_api_headers,
    )
    assert dw.status_code == 200
    dw_data = dw.json()

    assert dw_data["risk_score"] == risk_data["risk_score"]


@pytest.mark.asyncio
async def test_different_evidence_produces_different_score(monkeypatch, db_session):
    """Nothing forces every wallet through the same number: a wallet with
    starkly different on-chain evidence gets a genuinely different score
    and a different snapshot_id."""
    from app.schemas.common import Chain
    from app.services.risk_service import evaluate_wallet_risk

    _patch_deterministic_pipeline(monkeypatch, txs=_fixed_btc_txs())
    r_quiet = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)

    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    busy_txs = [
        RawTx(tx_hash=f"busyTx{i}", from_address=f"1Counterparty{i}", to_address="1BusyWallet",
              amount=50.0 + i, chain="BTC", timestamp=ts, asset="BTC")
        for i in range(40)
    ] + [
        RawTx(tx_hash="busyOut", from_address="1BusyWallet", to_address="1Cashout",
              amount=1500.0, chain="BTC", timestamp=ts, asset="BTC"),
    ]
    _patch_deterministic_pipeline(monkeypatch, txs=busy_txs)
    r_busy = await evaluate_wallet_risk(db_session, "1BusyWallet", Chain.BTC)

    assert r_quiet.risk_score != r_busy.risk_score
    assert r_quiet.snapshot_id != r_busy.snapshot_id


@pytest.mark.asyncio
async def test_new_evidence_snapshot_legitimately_changes_result(monkeypatch, db_session):
    """The SAME wallet address gets a new snapshot_id — and is allowed to
    get a new score — once its on-chain evidence actually changes. This is
    the one legitimate way a repeated call for the same address may not
    match a previous call."""
    from app.schemas.common import Chain
    from app.services.risk_service import evaluate_wallet_risk

    addr = "1EvolvingWallet"
    original_txs = _fixed_btc_txs()
    _patch_deterministic_pipeline(monkeypatch, txs=original_txs)
    r_before = await evaluate_wallet_risk(db_session, addr, Chain.BTC)

    new_txs = original_txs + [
        RawTx(tx_hash="newTx3", from_address="1SenderCCC", to_address=addr,
              amount=25.0, chain="BTC", timestamp=datetime(2024, 6, 1, tzinfo=timezone.utc), asset="BTC"),
    ]
    _patch_deterministic_pipeline(monkeypatch, txs=new_txs)
    r_after = await evaluate_wallet_risk(db_session, addr, Chain.BTC)

    assert r_before.snapshot_id != r_after.snapshot_id


@pytest.mark.asyncio
async def test_mixer_exposure_from_own_trace_raises_score(monkeypatch, db_session):
    """
    Regression: a wallet whose own persisted trace (app/engine/taint.py)
    reaches a known mixer used to score however the raw behavioral model
    felt like — 0.01-0.05/100 was observed live for demo wallets that trace
    straight to Tornado Cash — because the risk model never looked at Layer
    1's own findings for this exact wallet. It now does: a wallet with a
    MIXER_BOUNDARY terminal in its own trace is floored to HIGH and carries
    a "mixer_exposure" evidence item, on top of whatever the behavioral
    score alone would have said.
    """
    import uuid
    from datetime import datetime, timezone

    from app.models.engine import Anchor, TaintNode, Trace
    from app.schemas.common import Chain
    from app.services.risk_service import (
        MIXER_EXPOSURE_SCORE_FLOOR,
        evaluate_wallet_risk,
    )

    addr = "0xMixerExposedWallet"
    chain = "ETH"

    anchor = Anchor(
        id=uuid.uuid4(), case_id=None, address=addr, chain=chain,
        attestation_class="C", attestation_type="scenario",
        source_ref="test-mixer-exposure", asserted_by="test",
        asserted_at=datetime.now(timezone.utc), system_generated=False,
    )
    db_session.add(anchor)
    await db_session.flush()

    trace = Trace(id=uuid.uuid4(), anchor_id=anchor.id, reproducible_hash="a" * 64)
    db_session.add(trace)
    await db_session.flush()

    db_session.add_all([
        TaintNode(
            trace_id=trace.id, address=addr, chain=chain, hop=0,
            taint_fraction=1.0, tainted_value=1.0, terminal_kind=None,
        ),
        TaintNode(
            trace_id=trace.id, address="0xIntermediateHop", chain=chain, hop=1,
            taint_fraction=1.0, tainted_value=1.0, terminal_kind=None,
        ),
        TaintNode(
            trace_id=trace.id, address="0x12D66f87A04A9E220743712cE6d9bB1B5616B8Fc",
            chain=chain, hop=2, taint_fraction=1.0, tainted_value=0.1,
            terminal_kind="MIXER_BOUNDARY", entity_name="Tornado Cash 0.1 ETH",
        ),
    ])
    await db_session.commit()

    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    quiet_txs = [
        RawTx(tx_hash="mixTx1", from_address="0xSenderQuiet", to_address=addr,
              amount=1.0, chain="ETH", timestamp=ts, asset="ETH"),
    ]

    # _patch_deterministic_pipeline only wires up the BTC explorer (plus the
    # chain-agnostic graph-features/embedding fakes this ETH wallet also
    # needs) — give it a matching fake ETH explorer for this test.
    import app.services.risk_service as risk_service_module

    async def _fake_eth_get_transactions(address, limit=25):
        return list(quiet_txs)

    _patch_deterministic_pipeline(monkeypatch, txs=quiet_txs)
    monkeypatch.setattr(risk_service_module.eth_explorer, "get_transactions", _fake_eth_get_transactions)

    result = await evaluate_wallet_risk(db_session, addr, Chain.ETH)

    assert result.risk_score >= MIXER_EXPOSURE_SCORE_FLOOR
    feature_names = [e.feature_name for e in result.evidence]
    assert "mixer_exposure" in feature_names
    mixer_evidence = next(e for e in result.evidence if e.feature_name == "mixer_exposure")
    assert "Tornado Cash 0.1 ETH" in mixer_evidence.detail
    assert result.risk_source == "corroborated"


@pytest.mark.asyncio
async def test_typology_exposure_from_own_trace_raises_score(monkeypatch, db_session):
    """
    Regression: three seeded demo wallets whose own persisted trace showed a
    textbook rapid cash-out (funds reaching an exchange within minutes,
    "consistent with a pre-arranged cash-out" per the typology engine's own
    narrative) plus a fan-out to a dozen addresses still scored 5-8/100 LOW,
    because the risk model never looked at Layer 2's own typology findings
    for this exact wallet — only its raw transaction-shape features. Two or
    more independent qualifying patterns on the wallet's own trace now floor
    the score to HIGH, the same treatment already given to mixer exposure.
    """
    import uuid
    from datetime import datetime, timezone

    from app.models.engine import Anchor, Trace
    from app.schemas.common import Chain
    from app.services.risk_service import (
        TYPOLOGY_SCORE_FLOOR,
        evaluate_wallet_risk,
    )

    addr = "0xTypologyExposedWallet"
    chain = "ETH"

    anchor = Anchor(
        id=uuid.uuid4(), case_id=None, address=addr, chain=chain,
        attestation_class="C", attestation_type="scenario",
        source_ref="test-typology-exposure", asserted_by="test",
        asserted_at=datetime.now(timezone.utc), system_generated=False,
    )
    db_session.add(anchor)
    await db_session.flush()

    db_session.add(Trace(
        id=uuid.uuid4(), anchor_id=anchor.id, reproducible_hash="b" * 64,
        typologies=[
            {
                "code": "RAPID_TO_EXCHANGE", "label": "Rapid movement to exchange",
                "narrative": "Funds reached Binance within 11 minutes of the reported "
                "wallet receiving them — consistent with a pre-arranged cash-out.",
                "addresses": [],
            },
            {
                "code": "FAN_OUT", "label": "Fan-out distribution",
                "narrative": "One wallet distributed funds to 12 separate addresses.",
                "addresses": [],
            },
            {
                "code": "MULTI_HOP", "label": "Multi-hop layering",
                "narrative": "Funds passed through 5 hops.",
                "addresses": [],
            },
        ],
    ))
    await db_session.commit()

    ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
    quiet_txs = [
        RawTx(tx_hash="typTx1", from_address="0xSenderQuiet", to_address=addr,
              amount=1.0, chain="ETH", timestamp=ts, asset="ETH"),
    ]
    import app.services.risk_service as risk_service_module

    async def _fake_eth_get_transactions(address, limit=25):
        return list(quiet_txs)

    _patch_deterministic_pipeline(monkeypatch, txs=quiet_txs)
    monkeypatch.setattr(risk_service_module.eth_explorer, "get_transactions", _fake_eth_get_transactions)

    result = await evaluate_wallet_risk(db_session, addr, Chain.ETH)

    assert result.risk_score >= TYPOLOGY_SCORE_FLOOR
    feature_names = [e.feature_name for e in result.evidence]
    assert "laundering_pattern_exposure" in feature_names
    typo_evidence = next(e for e in result.evidence if e.feature_name == "laundering_pattern_exposure")
    assert "Rapid movement to exchange" in typo_evidence.detail
    assert "Fan-out distribution" in typo_evidence.detail
    # MULTI_HOP is deliberately not a qualifying code — too common in
    # legitimate use to be treated as laundering-pattern evidence.
    assert "Multi-hop layering" not in typo_evidence.detail
    assert result.risk_source == "corroborated"


@pytest.mark.asyncio
async def test_no_artificial_clamping_of_normal_scores(monkeypatch, db_session):
    """A genuine model probability strictly between 0 and 1 passes through
    untouched: no min/max clamp nudges it toward a round-looking number, and
    no floor/bonus applies when there's no sanctions match or complaint
    corroboration to justify one (this wallet has neither)."""
    from app.schemas.common import Chain
    from app.services import risk_service as risk_service_module

    _patch_deterministic_pipeline(monkeypatch)
    monkeypatch.setattr(risk_service_module, "predict_risk_score", lambda _vec: 0.543210)

    r = await risk_service_module.evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)
    assert r.risk_score == 0.5432  # rounded to 4dp only — nothing else touches it
    assert r.risk_tier == RiskTier.medium  # 0.30 <= score < 0.60, per map_score_to_tier


@pytest.mark.asyncio
async def test_shap_evidence_matches_the_scored_inference(monkeypatch, db_session):
    """SHAP evidence is computed from the exact model_vector that produced
    the displayed score, not a separately-fetched or re-derived one:
    re-running with identical evidence reproduces the identical evidence
    list, proving the two are coupled to one inference rather than able to
    silently drift apart."""
    from app.schemas.common import Chain
    from app.services.risk_service import evaluate_wallet_risk

    _patch_deterministic_pipeline(monkeypatch)
    r1 = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)
    r2 = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)

    assert len(r1.evidence) == len(r2.evidence) > 0
    for e1, e2 in zip(r1.evidence, r2.evidence):
        assert e1.feature_name == e2.feature_name
        assert e1.contribution == e2.contribution
        assert e1.direction == e2.direction


@pytest.mark.asyncio
async def test_model_and_schema_versions_are_present_and_traceable(monkeypatch, db_session):
    """Every scored response carries a model_version, feature_schema_version,
    snapshot_id and calculated_at — enough to confirm two results came from
    the same computation, or to explain precisely why they legitimately
    didn't."""
    from app.schemas.common import Chain
    from app.services.risk_service import evaluate_wallet_risk

    _patch_deterministic_pipeline(monkeypatch)
    r = await evaluate_wallet_risk(db_session, DETERMINISTIC_WALLET, Chain.BTC)

    assert r.model_version
    assert r.feature_schema_version
    assert r.snapshot_id
    assert r.calculated_at
