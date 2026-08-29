"""
app/tests/test_synthetic_generator.py — Verify synthetic generator and end-to-end correlation against planted data.
"""
from datetime import datetime
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint, ComplaintWallet
from app.models.wallet import Wallet
from scripts.generate_synthetic_ncrp import generate_synthetic_dataset, PLANTED_SHARED_WALLETS


def test_synthetic_generator_dataset_structure():
    dataset = generate_synthetic_dataset(seed=123, single_count=20)
    assert "wallets" in dataset
    assert "complaints" in dataset
    assert "complaint_wallets" in dataset
    assert dataset["metadata"]["total_complaints"] == 20 + sum(c["complaint_count"] for c in PLANTED_SHARED_WALLETS)
    assert dataset["metadata"]["planted_clusters_count"] == len(PLANTED_SHARED_WALLETS)


@pytest.mark.asyncio
async def test_planted_cluster_end_to_end_correlation(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
):
    """
    Seed the database with synthetic dataset and verify that querying the planted
    BTC syndicate wallet returns all 6 linked complaints and a high correlation score.
    """
    dataset = generate_synthetic_dataset(seed=42, single_count=10)

    # Populate DB with dataset
    for w in dataset["wallets"]:
        wallet = Wallet(
            id=uuid.UUID(w["id"]),
            address=w["address"],
            chain=w["chain"],
            risk_tier=w["risk_tier"],
        )
        db_session.add(wallet)

    for c in dataset["complaints"]:
        complaint = Complaint(
            id=uuid.UUID(c["id"]),
            ncrp_ref=c["ncrp_ref"],
            source_platform=c["source_platform"],
            narrative_text=c["narrative_text"],
            fraud_typology=c["fraud_typology"],
            amount_lost=c["amount_lost"],
            filed_at=datetime.fromisoformat(c["filed_at"]),
            state=c["state"],
            district=c["district"],
            created_at=datetime.fromisoformat(c["created_at"]),
        )
        db_session.add(complaint)

    for cw in dataset["complaint_wallets"]:
        link = ComplaintWallet(
            complaint_id=uuid.UUID(cw["complaint_id"]),
            wallet_id=uuid.UUID(cw["wallet_id"]),
            reported_at=datetime.fromisoformat(cw["reported_at"]),
        )
        db_session.add(link)

    await db_session.commit()

    # Query planted cluster 1: "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2" (BTC)
    planted_btc = PLANTED_SHARED_WALLETS[0]
    resp = await client.post(
        "/api/v1/correlate",
        json={"address": planted_btc["address"], "chain": planted_btc["chain"]},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["linked_complaints"]) == 6
    assert data["distinct_geographies"] >= 4
    assert data["correlation_score"] >= 0.90
    assert data["total_amount"] > 1000000.0

    # Query planted cluster 2: "0x742d35Cc6634C0532925a3b844Bc454e4438f44e" (ETH)
    planted_eth = PLANTED_SHARED_WALLETS[1]
    resp2 = await client.post(
        "/api/v1/correlate",
        json={"address": planted_eth["address"], "chain": planted_eth["chain"]},
        headers=auth_headers,
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert len(data2["linked_complaints"]) == 4
    assert data2["distinct_geographies"] >= 3
    assert data2["correlation_score"] >= 0.85
