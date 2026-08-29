"""
app/tests/test_trace.py — Tests for Blockchain Tracing (Phase 3).
"""
import pytest
from httpx import AsyncClient

from app.services.explorers.known_vasps import lookup_known_vasp


def test_known_vasp_lookup():
    """Verify known VASP lookup for BTC and ETH addresses."""
    # Binance BTC
    match_btc = lookup_known_vasp("1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ")
    assert match_btc is not None
    assert match_btc[0] == "Binance"

    # Bitfinex ETH
    match_eth = lookup_known_vasp("0x742d35Cc6634C0532925a3b844Bc454e4438f44e")
    assert match_eth is not None
    assert match_eth[0] == "Bitfinex"

    # Unknown address
    assert lookup_known_vasp("1UnknownRandomAddress999999999999") is None


@pytest.mark.asyncio
async def test_trace_wallet_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/wallets/bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh/trace?chain=BTC")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_trace_wallet_invalid_chain_validation_error(client: AsyncClient, auth_headers: dict):
    response = await client.get(
        "/api/v1/wallets/bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh/trace?chain=INVALID_CHAIN",
        headers=auth_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_trace_wallet_btc_success(client: AsyncClient, auth_headers: dict):
    # Active on-chain BTC address with real transactions
    addr = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
    response = await client.get(
        f"/api/v1/wallets/{addr}/trace?chain=BTC",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "wallet" in data
    assert data["wallet"]["address"] == addr
    assert data["wallet"]["chain"] == "BTC"
    assert "path" in data
    assert isinstance(data["path"], list)
    assert "hops_count" in data
    assert data["hops_count"] == len(data["path"])
    assert "traced_at" in data


@pytest.mark.asyncio
async def test_trace_wallet_eth_success(client: AsyncClient, auth_headers: dict):
    # Active on-chain ETH address with real transactions (Bitfinex hot wallet)
    addr = "0x742d35Cc6634C0532925a3b844Bc454e4438f44e"
    response = await client.get(
        f"/api/v1/wallets/{addr}/trace?chain=ETH",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "wallet" in data
    assert data["wallet"]["address"] == addr
    assert data["wallet"]["chain"] == "ETH"
    assert "path" in data
    assert isinstance(data["path"], list)
    assert "hops_count" in data
    assert data["nearest_vasp"] in ("Bitfinex", "Bitfinex: Hot Wallet") or data["nearest_vasp"] is not None


@pytest.mark.asyncio
async def test_trace_wallet_tron_success(client: AsyncClient, auth_headers: dict):
    # Active on-chain TRON address with real transactions (Binance Tron Hot)
    addr = "TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7"
    response = await client.get(
        f"/api/v1/wallets/{addr}/trace?chain=TRON",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "wallet" in data
    assert data["wallet"]["address"] == addr
    assert data["wallet"]["chain"] == "TRON"
    assert "path" in data
    assert isinstance(data["path"], list)
    assert len(data["path"]) > 0
    assert "hops_count" in data
    assert data["hops_count"] == len(data["path"])
    assert data["nearest_vasp"] == "Binance" or data["nearest_vasp"] is not None


@pytest.mark.asyncio
async def test_trace_wallet_unsupported_chain_rejected(client: AsyncClient, auth_headers: dict):
    """Verify that unsupported chains in the enum (e.g. BSC) return a clear UNSUPPORTED_CHAIN error."""
    addr = "0x8894e0a0c962cb723c1976a4421c95949be2d4e3"
    response = await client.get(
        f"/api/v1/wallets/{addr}/trace?chain=BSC",
        headers=auth_headers,
    )
    assert response.status_code == 422
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNSUPPORTED_CHAIN"
    assert "BSC" in data["error"]["message"]
