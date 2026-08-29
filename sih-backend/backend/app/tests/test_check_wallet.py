"""
app/tests/test_check_wallet.py — Tests for POST /check-wallet (VASP Chokepoint).
"""
import time
import pytest
from httpx import AsyncClient

from app.schemas.common import RiskTier
from app.services import registry_service
from app.tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_check_wallet_unauthorized_missing_api_key(client: AsyncClient):
    response = await client.post(
        "/check-wallet",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": 1.0},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_check_wallet_unauthorized_invalid_api_key(client: AsyncClient):
    response = await client.post(
        "/check-wallet",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": 1.0},
        headers={"X-API-Key": "wrong_key_123"},
    )
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_check_wallet_unflagged_address_allows_deposit(
    client: AsyncClient,
    vasp_api_headers: dict,
):
    response = await client.post(
        "/check-wallet",
        json={"address": "1CleanWalletAddress111111111111", "chain": "BTC", "amount": 0.5},
        headers=vasp_api_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "allow"
    assert data["risk_score"] == 0.0
    assert data["case_ref"] is None


@pytest.mark.asyncio
async def test_check_wallet_critical_address_blocks_deposit(
    client: AsyncClient,
    fake_redis: FakeRedis,
    vasp_api_headers: dict,
):
    # Pre-populate critical wallet in Redis
    addr = "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2"
    chain = "BTC"
    await registry_service.set_risk_entry(
        redis_client=fake_redis,
        chain=chain,
        address=addr,
        score=0.95,
        tier=RiskTier.critical,
        case_ref="NCRP-2026-001001",
    )

    response = await client.post(
        "/check-wallet",
        json={"address": addr, "chain": chain, "amount": 2.5},
        headers=vasp_api_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "block"
    assert data["risk_score"] == 0.95
    assert data["case_ref"] == "NCRP-2026-001001"


@pytest.mark.asyncio
async def test_check_wallet_high_risk_holds_deposit(
    client: AsyncClient,
    fake_redis: FakeRedis,
    vasp_api_headers: dict,
):
    addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    chain = "ETH"
    await registry_service.set_risk_entry(
        redis_client=fake_redis,
        chain=chain,
        address=addr,
        score=0.75,
        tier=RiskTier.high,
        case_ref="NCRP-2026-001002",
    )

    response = await client.post(
        "/check-wallet",
        json={"address": addr, "chain": chain, "amount": 10.0},
        headers=vasp_api_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "hold"
    assert data["risk_score"] == 0.75
    assert data["case_ref"] == "NCRP-2026-001002"


@pytest.mark.asyncio
async def test_check_wallet_validation_error_on_invalid_amount(
    client: AsyncClient,
    vasp_api_headers: dict,
):
    response = await client.post(
        "/check-wallet",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": -1.0},
        headers=vasp_api_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_check_wallet_latency_benchmark(
    client: AsyncClient,
    fake_redis: FakeRedis,
    vasp_api_headers: dict,
):
    """Verify that hot-path execution time is well under 200ms."""
    start = time.perf_counter()
    response = await client.post(
        "/check-wallet",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": 1.0},
        headers=vasp_api_headers,
    )
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    assert response.status_code == 200
    assert elapsed_ms < 200.0, f"Hot path latency was {elapsed_ms:.2f}ms, expected < 200ms"
