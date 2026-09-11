"""
app/tests/test_rbac.py — RBAC enforcement regression test.

Before this fix, require_auth() decoded the JWT's role claim but nothing
ever checked it against the endpoint's required roles — any authenticated
token (including compliance_viewer, read-only per PRD §5) could POST
complaints, POST correlate, or PATCH a case's status. These tests pin the
fix (app/api/v1/deps.py::require_role) and guard against regression.
"""
import pytest
from httpx import AsyncClient

from app.core.security import create_access_token


def _viewer_headers() -> dict[str, str]:
    token = create_access_token(subject="viewer@i4c.gov.in", role="compliance_viewer")
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_compliance_viewer_cannot_create_complaint(client: AsyncClient):
    response = await client.post(
        "/api/v1/complaints",
        headers=_viewer_headers(),
        json={
            "source_platform": "manual",
            "narrative_text": "test",
            "fraud_typology": "investment_scam",
            "amount_lost": 1000,
            "filed_at": "2026-09-11T00:00:00Z",
            "state": "MH",
            "district": "Pune",
        },
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_compliance_viewer_cannot_run_correlate(client: AsyncClient):
    response = await client.post(
        "/api/v1/correlate",
        headers=_viewer_headers(),
        json={"address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh", "chain": "BTC"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_compliance_viewer_cannot_create_case(client: AsyncClient):
    response = await client.post(
        "/api/v1/cases", headers=_viewer_headers(), json={},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_compliance_viewer_cannot_register_anchor(client: AsyncClient):
    response = await client.post(
        "/api/v1/anchors",
        headers=_viewer_headers(),
        json={
            "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "chain": "BTC",
            "attestation_class": "A",
            "attestation_type": "LEGAL_COMPLAINT",
            "source_ref": "NCRP-TEST-001",
            "asserted_by": "victim-uuid",
        },
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_compliance_viewer_can_still_list_cases(client: AsyncClient):
    """Read-only endpoints remain open to any authenticated role (PRD §5: 'any')."""
    response = await client.get("/api/v1/cases", headers=_viewer_headers())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_investigator_can_register_anchor(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/anchors",
        headers=auth_headers,
        json={
            "address": "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            "chain": "BTC",
            "attestation_class": "A",
            "attestation_type": "LEGAL_COMPLAINT",
            "source_ref": "NCRP-TEST-002",
            "asserted_by": "victim-uuid",
        },
    )
    assert response.status_code == 201
    assert response.json()["attestation_class"] == "A"
