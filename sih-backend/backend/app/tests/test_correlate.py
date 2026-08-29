"""
app/tests/test_correlate.py — Tests for Cross-Victim Correlation Engine (USP 1).
"""
import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint, ComplaintWallet
from app.models.wallet import Wallet
from app.services.correlation_service import calculate_correlation_score


def test_calculate_correlation_score_math():
    """Verify deterministic scoring curve."""
    assert calculate_correlation_score(0, 0) == 0.0
    assert calculate_correlation_score(1, 1) == 0.10
    # 2 complaints, 1 state vs 2 states
    assert calculate_correlation_score(2, 1) == 0.55
    assert calculate_correlation_score(2, 2) == 0.60
    # 3 complaints, 1 state vs 3 states
    assert calculate_correlation_score(3, 1) == 0.75
    assert calculate_correlation_score(3, 3) == 0.85
    # 6 complaints, 5 states -> min(1.0, 0.85 + 0.12 + 0.10) = 1.0
    assert calculate_correlation_score(6, 5) == 1.0


@pytest.mark.asyncio
async def test_correlate_wallet_by_address_and_chain(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
):
    # Setup test wallet in DB
    w_id = uuid.uuid4()
    address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2"
    chain = "BTC"

    wallet = Wallet(
        id=w_id,
        address=address,
        chain=chain,
        risk_tier="critical",
    )
    db_session.add(wallet)

    # Attach 3 complaints from 2 states
    complaint_ids = []
    for i, (state, amt) in enumerate([
        ("Maharashtra", 100000.0),
        ("Karnataka", 200000.0),
        ("Maharashtra", 150000.0),
    ]):
        c_id = uuid.uuid4()
        complaint_ids.append(c_id)
        c = Complaint(
            id=c_id,
            ncrp_ref=f"NCRP-2026-CORR{i:02d}",
            source_platform="ncrp",
            fraud_typology="investment_fraud",
            amount_lost=amt,
            filed_at=datetime.now(timezone.utc),
            state=state,
            district="DistrictTest",
        )
        db_session.add(c)
        cw = ComplaintWallet(
            complaint_id=c_id,
            wallet_id=w_id,
        )
        db_session.add(cw)

    await db_session.commit()

    # Query /api/v1/correlate by address + chain
    response = await client.post(
        "/api/v1/correlate",
        json={"address": address, "chain": chain},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["correlation_score"] == 0.80  # 3 complaints, 2 states -> 0.70 + 0.05*2 = 0.80
    assert len(data["linked_complaints"]) == 3
    assert data["distinct_geographies"] == 2
    assert data["total_amount"] == 450000.0


@pytest.mark.asyncio
async def test_correlate_wallet_by_wallet_id(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
):
    w_id = uuid.uuid4()
    wallet = Wallet(
        id=w_id,
        address="0x742d35Cc6634C0532925a3b844Bc454e4438f44e",
        chain="ETH",
    )
    db_session.add(wallet)
    await db_session.commit()

    response = await client.post(
        "/api/v1/correlate",
        json={"wallet_id": str(w_id)},
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["correlation_score"] == 0.0
    assert len(data["linked_complaints"]) == 0
    assert data["distinct_geographies"] == 0
    assert data["total_amount"] == 0.0


@pytest.mark.asyncio
async def test_correlate_wallet_not_found(client: AsyncClient, auth_headers: dict):
    response = await client.post(
        "/api/v1/correlate",
        json={"address": "non_existent_addr", "chain": "BTC"},
        headers=auth_headers,
    )
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "WALLET_NOT_FOUND"


@pytest.mark.asyncio
async def test_correlate_wallet_invalid_params_validation(client: AsyncClient, auth_headers: dict):
    # Both wallet_id and address provided
    response = await client.post(
        "/api/v1/correlate",
        json={
            "wallet_id": str(uuid.uuid4()),
            "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2",
            "chain": "BTC",
        },
        headers=auth_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
