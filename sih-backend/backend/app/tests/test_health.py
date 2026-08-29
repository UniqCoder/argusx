"""
app/tests/test_health.py — Tests for the /health endpoint.

This is the Phase 0 acceptance test — it must pass before Phase 0 is marked Done.
The health endpoint is reachable without auth.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_shape(client: AsyncClient):
    response = await client.get("/health")
    data = response.json()
    assert "status" in data
    assert "version" in data
    assert "services" in data
    assert data["status"] in ("ok", "degraded")


@pytest.mark.asyncio
async def test_health_no_auth_required(client: AsyncClient):
    """Health must be reachable without any Authorization header."""
    response = await client.get("/health")
    assert response.status_code != 401
