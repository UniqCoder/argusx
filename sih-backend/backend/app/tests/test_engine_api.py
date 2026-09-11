"""
app/tests/test_engine_api.py — end-to-end HTTP tests for the new ARGUS v2
engine endpoints (anchors + trace + decisions + ledger verify).

Confirms the new routes are wired correctly through main.py and that a full
anchor -> trace -> decision -> ledger cycle works over the API, without
touching any existing v1 endpoint's behavior.
"""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from app.engine import taint as taint_module
from app.schemas.common import Chain
from app.services.explorers.base import RawTx

ANCHOR_ADDR = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
VASP_ADDR = "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ"  # curated Binance BTC address
_NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)


async def _fake_get_transactions(address: str, limit: int = 25) -> list[RawTx]:
    if address == ANCHOR_ADDR:
        return [
            RawTx(tx_hash="tx1", from_address=ANCHOR_ADDR, to_address=VASP_ADDR,
                  amount=0.5, chain=Chain.BTC, timestamp=_NOW),
        ]
    return []


@pytest.fixture(autouse=True)
def _patch_explorer(monkeypatch):
    monkeypatch.setattr(taint_module._btc, "get_transactions", _fake_get_transactions)


@pytest.mark.asyncio
async def test_anchor_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/anchors", json={
        "address": ANCHOR_ADDR, "chain": "BTC", "attestation_class": "A",
        "attestation_type": "LEGAL_COMPLAINT", "source_ref": "NCRP-1", "asserted_by": "v1",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_full_anchor_trace_decision_ledger_cycle(client: AsyncClient, auth_headers: dict):
    # 1. Register a Class-A anchor (victim complaint)
    anchor_resp = await client.post(
        "/api/v1/anchors",
        headers=auth_headers,
        json={
            "address": ANCHOR_ADDR, "chain": "BTC", "attestation_class": "A",
            "attestation_type": "LEGAL_COMPLAINT", "source_ref": "NCRP-2026-E2E",
            "asserted_by": "victim-uuid-1", "victim_amount_inr": 100000,
        },
    )
    assert anchor_resp.status_code == 201
    anchor = anchor_resp.json()

    # 2. Run a trace from that anchor
    trace_resp = await client.post(
        "/api/v1/engine/trace",
        headers=auth_headers,
        json={"anchor_id": anchor["id"], "method": "haircut", "max_hops": 4, "max_nodes": 20},
    )
    assert trace_resp.status_code == 201
    trace = trace_resp.json()
    assert trace["node_count"] >= 1
    vasp_terminals = [n for n in trace["terminals"] if n["terminal_kind"] == "VASP"]
    assert len(vasp_terminals) == 1
    assert vasp_terminals[0]["entity_name"] == "Binance"
    # tainted_inr is fraction-of-reported-loss, computed with no price oracle
    assert vasp_terminals[0]["tainted_inr"] is not None

    # 3. Fetch the persisted trace back
    get_resp = await client.get(f"/api/v1/engine/trace/{trace['trace_id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["reproducible_hash"] == trace["reproducible_hash"]

    # 4. Proof bundle exposes the tx-hash path
    proof_resp = await client.get(f"/api/v1/engine/trace/{trace['trace_id']}/proof", headers=auth_headers)
    assert proof_resp.status_code == 200
    assert VASP_ADDR in proof_resp.json()["proof_paths"]
    assert proof_resp.json()["proof_paths"][VASP_ADDR] == ["tx1"]

    # 5. A qualifying block decision was issued (Class-A anchor + trace + VASP terminal)
    #    Find it by re-deriving from the ledger verify + decisions endpoint isn't listed
    #    directly by trace, so assert via the ledger that a decision_issued event fired.
    ledger_resp = await client.get("/api/v1/engine/ledger/verify", headers=auth_headers)
    assert ledger_resp.status_code == 200
    assert ledger_resp.json()["intact"] is True
    assert ledger_resp.json()["entries_checked"] >= 3  # anchor_registered, trace_completed, decision_issued


@pytest.mark.asyncio
async def test_get_trace_with_non_vasp_terminal(client: AsyncClient, auth_headers: dict):
    """Regression test: GET /trace/{id} 500'd in production (real Postgres) for any
    terminal node that isn't VASP/MIXER_BOUNDARY (e.g. DEPTH_LIMIT, DUST, NODE_LIMIT)
    because the unattributed_residual/mixer_total sums read `.taint_value` instead of
    the TaintNodeRead schema field `.tainted_value`. The existing e2e cycle test never
    caught this because its only terminal was VASP, which the buggy sum's filter
    excludes outright — the generator was never evaluated, so the AttributeError
    never fired. This anchor has zero outgoing transactions, so its only node is a
    non-VASP terminal, forcing the sum to actually iterate and touch the field.
    """
    zero_activity_addr = "bc1qzeroactivitywallettestcase0000000000"
    anchor_resp = await client.post(
        "/api/v1/anchors",
        headers=auth_headers,
        json={
            "address": zero_activity_addr, "chain": "BTC", "attestation_class": "A",
            "attestation_type": "LEGAL_COMPLAINT", "source_ref": "NCRP-2026-ZEROTX",
            "asserted_by": "victim-uuid-2",
        },
    )
    assert anchor_resp.status_code == 201
    anchor = anchor_resp.json()

    trace_resp = await client.post(
        "/api/v1/engine/trace",
        headers=auth_headers,
        json={"anchor_id": anchor["id"], "method": "haircut", "max_hops": 3, "max_nodes": 10},
    )
    assert trace_resp.status_code == 201
    trace = trace_resp.json()
    assert trace["node_count"] == 1
    assert trace["terminals"][0]["terminal_kind"] not in ("VASP", "MIXER_BOUNDARY")

    get_resp = await client.get(f"/api/v1/engine/trace/{trace['trace_id']}", headers=auth_headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["reproducible_hash"] == trace["reproducible_hash"]
    assert float(body["unattributed_residual"]) == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_trace_unknown_anchor_returns_404(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/engine/trace",
        headers=auth_headers,
        json={"anchor_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ANCHOR_NOT_FOUND"


@pytest.mark.asyncio
async def test_duplicate_anchor_rejected(client: AsyncClient, auth_headers: dict):
    body = {
        "address": ANCHOR_ADDR, "chain": "BTC", "attestation_class": "B",
        "attestation_type": "PUBLIC_ATTRIBUTED_REPORT", "source_ref": "ransomwhere-1",
        "asserted_by": "ransomwhe.re",
    }
    first = await client.post("/api/v1/anchors", headers=auth_headers, json=body)
    assert first.status_code == 201
    second = await client.post("/api/v1/anchors", headers=auth_headers, json=body)
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "DUPLICATE_ANCHOR"
