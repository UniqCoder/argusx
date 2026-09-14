"""
app/tests/test_complaints.py — Tests for complaint ingestion and listing APIs.
"""
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_complaint_success(client: AsyncClient, auth_headers: dict):
    payload = {
        "ncrp_ref": "NCRP-2026-TEST01",
        "source_platform": "ncrp",
        "narrative_text": "Victim reported ₹1.5L lost in crypto investment scam.",
        "fraud_typology": "investment_fraud",
        "amount_lost": 150000.0,
        "filed_at": datetime.now(timezone.utc).isoformat(),
        "state": "Maharashtra",
        "district": "Mumbai",
    }
    response = await client.post(
        "/api/v1/complaints",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["ncrp_ref"] == payload["ncrp_ref"]
    assert data["source_platform"] == payload["source_platform"]
    assert data["fraud_typology"] == payload["fraud_typology"]
    assert data["amount_lost"] == payload["amount_lost"]
    assert data["state"] == payload["state"]
    assert data["district"] == payload["district"]
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_complaint_validation_error(client: AsyncClient, auth_headers: dict):
    # Missing required field source_platform and invalid filed_at
    payload = {
        "amount_lost": 5000.0,
    }
    response = await client.post(
        "/api/v1/complaints",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_create_complaint_unauthorized(client: AsyncClient):
    payload = {
        "source_platform": "ncrp",
        "filed_at": datetime.now(timezone.utc).isoformat(),
    }
    response = await client.post(
        "/api/v1/complaints",
        json=payload,
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_list_complaints_with_filtering(client: AsyncClient, auth_headers: dict):
    # Create 3 complaints
    for i, (st, typ) in enumerate([
        ("Maharashtra", "investment_fraud"),
        ("Karnataka", "investment_fraud"),
        ("Maharashtra", "sextortion"),
    ]):
        await client.post(
            "/api/v1/complaints",
            json={
                "ncrp_ref": f"NCRP-2026-LIST{i:02d}",
                "source_platform": "sahyog",
                "fraud_typology": typ,
                "amount_lost": 50000.0 * (i + 1),
                "filed_at": datetime.now(timezone.utc).isoformat(),
                "state": st,
                "district": "TestDistrict",
            },
            headers=auth_headers,
        )

    # 1. List all
    resp = await client.get("/api/v1/complaints", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3
    assert data["page"] == 1
    assert data["page_size"] == 25

    # 2. Filter by state
    resp_state = await client.get("/api/v1/complaints?state=Maharashtra", headers=auth_headers)
    assert resp_state.status_code == 200
    data_state = resp_state.json()
    assert data_state["total"] == 2
    assert len(data_state["items"]) == 2

    # 3. Filter by typology
    resp_typ = await client.get("/api/v1/complaints?fraud_typology=sextortion", headers=auth_headers)
    assert resp_typ.status_code == 200
    data_typ = resp_typ.json()
    assert data_typ["total"] == 1
    assert data_typ["items"][0]["fraud_typology"] == "sextortion"


@pytest.mark.asyncio
async def test_create_complaint_with_wallets_enables_correlation(
    client: AsyncClient, auth_headers: dict
):
    """
    The real regression this closes: before ComplaintCreate.wallets existed,
    POST /api/v1/complaints wrote only the complaint row, so
    complaint_wallets -- the only table POST /api/v1/correlate reads -- had no
    writer outside a synthetic seed script. Two complaints naming the same
    wallet here must produce a correlate hit with correlation_score > 0.
    """
    address = "0xTESTCORR00000000000000000000000000001"
    shared_wallet = {"address": address, "chain": "ETH"}

    for ref in ("NCRP-2026-CORR01", "NCRP-2026-CORR02"):
        payload = {
            "ncrp_ref": ref,
            "source_platform": "ncrp",
            "narrative_text": "Task-based job fraud.",
            "fraud_typology": "task_fraud",
            "amount_lost": 50000.0,
            "filed_at": datetime.now(timezone.utc).isoformat(),
            "state": "Delhi",
            "district": "New Delhi",
            "wallets": [shared_wallet],
        }
        response = await client.post("/api/v1/complaints", json=payload, headers=auth_headers)
        assert response.status_code == 201, response.text

    correlate_response = await client.post(
        "/api/v1/correlate",
        json={"address": address, "chain": "ETH"},
        headers=auth_headers,
    )
    assert correlate_response.status_code == 200, correlate_response.text
    data = correlate_response.json()
    assert len(data["linked_complaints"]) == 2
    assert data["correlation_score"] > 0.0


@pytest.mark.asyncio
async def test_correlate_matches_address_case_insensitively(
    client: AsyncClient, auth_headers: dict
):
    """EVM addresses are case-insensitive on-chain; a checksummed paste and a
    lowercase paste of the same wallet must correlate as one wallet, not two."""
    mixed_case = "0xAbCdEf0000000000000000000000000000CAFE"
    payload = {
        "ncrp_ref": "NCRP-2026-CASE01",
        "source_platform": "ncrp",
        "filed_at": datetime.now(timezone.utc).isoformat(),
        "wallets": [{"address": mixed_case, "chain": "ETH"}],
    }
    response = await client.post("/api/v1/complaints", json=payload, headers=auth_headers)
    assert response.status_code == 201, response.text

    correlate_response = await client.post(
        "/api/v1/correlate",
        json={"address": mixed_case.lower(), "chain": "ETH"},
        headers=auth_headers,
    )
    assert correlate_response.status_code == 200, correlate_response.text
    assert len(correlate_response.json()["linked_complaints"]) == 1
