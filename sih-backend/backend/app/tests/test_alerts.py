"""
app/tests/test_alerts.py — Tests for Alert registry and Celery notification task.
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.models.wallet import Wallet
from app.schemas.common import AlertAction, TriggeredBy
from app.services import alert_service
from app.workers.tasks.alerts import _process_alert_async


@pytest.mark.asyncio
async def test_list_alerts_empty(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/alerts", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


@pytest.mark.asyncio
async def test_list_alerts_with_resolved_filtering(
    client: AsyncClient,
    db_session: AsyncSession,
    auth_headers: dict,
):
    # Create wallet
    w_id = uuid.uuid4()
    wallet = Wallet(id=w_id, address="1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2", chain="BTC")
    db_session.add(wallet)
    await db_session.commit()

    # Create 2 alerts: one unresolved, one resolved
    a1 = await alert_service.create_alert(
        db=db_session,
        wallet_id=w_id,
        triggered_by=TriggeredBy.check_wallet_hook,
        action=AlertAction.block,
    )
    a2 = await alert_service.create_alert(
        db=db_session,
        wallet_id=w_id,
        triggered_by=TriggeredBy.check_wallet_hook,
        action=AlertAction.hold,
    )
    await alert_service.resolve_alert(db=db_session, alert_id=a2.id)

    # 1. Query all
    resp_all = await client.get("/api/v1/alerts", headers=auth_headers)
    assert resp_all.status_code == 200
    data_all = resp_all.json()
    assert data_all["total"] == 2

    # 2. Query open / unresolved only
    resp_open = await client.get("/api/v1/alerts?resolved=false", headers=auth_headers)
    assert resp_open.status_code == 200
    data_open = resp_open.json()
    assert data_open["total"] == 1
    assert data_open["items"][0]["action"] == "block"
    assert data_open["items"][0]["resolved_at"] is None

    # 3. Query resolved only
    resp_res = await client.get("/api/v1/alerts?resolved=true", headers=auth_headers)
    assert resp_res.status_code == 200
    data_res = resp_res.json()
    assert data_res["total"] == 1
    assert data_res["items"][0]["action"] == "hold"
    assert data_res["items"][0]["resolved_at"] is not None


@pytest.mark.asyncio
async def test_list_alerts_unauthorized(client: AsyncClient):
    response = await client.get("/api/v1/alerts")
    assert response.status_code == 401
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "UNAUTHORIZED"
