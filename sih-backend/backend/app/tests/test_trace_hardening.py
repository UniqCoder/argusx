"""
app/tests/test_trace_hardening.py — regression tests for the trace/risk
hardening fixes:

  1. An explorer outage during taint propagation must surface as the
     EXPLORER_UNAVAILABLE terminal (retryable infrastructure condition),
     not as DEPTH_LIMIT (which misreported outages as honest depth limits).
  2. Missing ML artifacts in GET /wallets/{addr}/risk must return the API
     contract's "unknown" tier with HTTP 200, not a generic HTTP 500.
  3. Per-chain anchor shape validation rejects malformed addresses with 422
     (mirrors src/lib/address.ts on the frontend).
"""
import pytest
from httpx import AsyncClient

from app.engine import taint as taint_module
from app.engine.taint import propagate_taint
from app.schemas.engine import TaintMethod, is_valid_anchor_shape
from app.services import risk_service
from app.services.explorers.base import ExplorerUnavailableError

# Shape-valid bech32 test address (same one test_engine_api uses).
BTC_ADDR = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"


# ── 1. Explorer outage during taint propagation ──────────────────────────────


@pytest.mark.asyncio
async def test_explorer_outage_surfaces_as_explorer_unavailable(monkeypatch):
    async def _raise(address: str, limit: int = 25):
        raise ExplorerUnavailableError(f"explorer down for {address}")

    monkeypatch.setattr(taint_module._btc, "get_transactions", _raise)

    result = await propagate_taint(
        anchor_address=BTC_ADDR,
        anchor_chain="BTC",
        anchor_taint_value=1.0,
        method=TaintMethod.haircut,
        max_hops=6,
        max_nodes=60,
        dilution_floor=0.005,
    )

    assert len(result.nodes) == 1
    node = result.nodes[0]
    assert node.terminal_kind == "EXPLORER_UNAVAILABLE"
    assert node.still_active is True


# ── 2. Missing ML artifacts -> unknown tier (200), never a 500 ───────────────


@pytest.mark.asyncio
async def test_risk_returns_unknown_tier_when_ml_artifacts_missing(
    client: AsyncClient,
    auth_headers: dict,
    monkeypatch,
):
    async def _ok_txs(address: str, limit: int = 25):
        return []

    def _boom(vector):
        raise FileNotFoundError(
            "Preprocessed data not found. Run preprocess.py first."
        )

    monkeypatch.setattr(risk_service.btc_explorer, "get_transactions", _ok_txs)
    monkeypatch.setattr(risk_service, "predict_risk_score", _boom)

    resp = await client.get(
        f"/api/v1/wallets/{BTC_ADDR}/risk?chain=BTC",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["risk_score"] is None
    assert data["risk_tier"] == "unknown"
    assert data["evidence"] == []


# ── 3. Per-chain anchor shape validation ─────────────────────────────────────


def test_is_valid_anchor_shape_matrix():
    # ETH: 0x + 40 hex
    assert is_valid_anchor_shape("ETH", "0x" + "Ab" * 20)
    assert not is_valid_anchor_shape("ETH", "0xE3B9...2D4A")  # elided copy
    assert not is_valid_anchor_shape("ETH", "0x123")  # too short
    # TRON: T + 33 base58
    assert is_valid_anchor_shape("TRON", "TTaTPaA1TnQcXwCJ1jbMfkiUKdmuhVbUk6")
    assert not is_valid_anchor_shape("TRON", "0x" + "a" * 40)
    # BTC: base58 or bech32
    assert is_valid_anchor_shape("BTC", "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo")
    assert is_valid_anchor_shape("BTC", BTC_ADDR)
    assert not is_valid_anchor_shape(
        "BTC", "bc1qzeroactivitywallettestcase0000000000"
    )  # contains bech32-invalid i/o/b


@pytest.mark.asyncio
async def test_anchor_rejects_malformed_address(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/anchors",
        headers=auth_headers,
        json={
            "address": "0xE3B9...2D4A",
            "chain": "ETH",
            "attestation_class": "C",
            "attestation_type": "INVESTIGATOR_ASSERTED",
            "source_ref": "MALFORMED-SHAPE-1",
            "asserted_by": "test",
        },
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_anchor_accepts_shape_valid_address(
    client: AsyncClient, auth_headers: dict
):
    resp = await client.post(
        "/api/v1/anchors",
        headers=auth_headers,
        json={
            "address": "0x" + "a" * 40,
            "chain": "ETH",
            "attestation_class": "C",
            "attestation_type": "INVESTIGATOR_ASSERTED",
            "source_ref": "SHAPE-OK-1",
            "asserted_by": "test",
        },
    )
    assert resp.status_code == 201
