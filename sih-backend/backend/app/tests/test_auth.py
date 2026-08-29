"""
app/tests/test_auth.py — Tests for JWT auth endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_login_with_dev_credentials(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "investigator@i4c.gov.in", "password": "devpass"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["role"] == "investigator"


@pytest.mark.asyncio
async def test_login_with_bad_credentials_returns_401(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "wrong@i4c.gov.in", "password": "wrong"},
    )
    assert response.status_code == 401
    data = response.json()
    # Must use the standard error envelope
    assert "error" in data
    assert data["error"]["code"] == "INVALID_CREDENTIALS"


@pytest.mark.asyncio
async def test_refresh_with_valid_token(client: AsyncClient):
    # First get a refresh token
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "investigator@i4c.gov.in", "password": "devpass"},
    )
    refresh_token = login_resp.json()["refresh_token"]

    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
        headers={"Authorization": f"Bearer {refresh_token}"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_401(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "not.a.real.token"},
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_without_token_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/complaints")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_check_wallet_rejects_jwt_bearer_token(client: AsyncClient, auth_headers: dict):
    """Verify that /check-wallet exclusively requires X-API-Key and rejects JWT Bearer tokens."""
    response = await client.post(
        "/check-wallet",
        json={"address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", "chain": "BTC", "amount": 1.0},
        headers=auth_headers,  # Has Authorization: Bearer <token>, lacks X-API-Key
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_API_KEY"


@pytest.mark.asyncio
async def test_jwt_protected_routes_reject_vasp_api_key(client: AsyncClient, vasp_api_headers: dict):
    """Verify that /api/v1/* routes exclusively require JWT Bearer and reject X-API-Key."""
    response = await client.get(
        "/api/v1/cases",
        headers=vasp_api_headers,  # Has X-API-Key, lacks Bearer JWT
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
