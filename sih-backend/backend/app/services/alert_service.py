"""
app/services/alert_service.py — Alert registry service.

Handles alert recording and query filtering (polled by frontend Alerts screen).
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.alert import Alert
from app.schemas.common import AlertAction, TriggeredBy


async def create_alert(
    db: AsyncSession,
    wallet_id: uuid.UUID,
    triggered_by: str | TriggeredBy,
    action: str | AlertAction,
    case_id: Optional[uuid.UUID] = None,
) -> Alert:
    """Create a new alert record in PostgreSQL."""
    action_val = action.value if isinstance(action, AlertAction) else str(action)
    triggered_val = triggered_by.value if isinstance(triggered_by, TriggeredBy) else str(triggered_by)

    alert = Alert(
        id=uuid.uuid4(),
        wallet_id=wallet_id,
        case_id=case_id,
        triggered_by=triggered_val,
        action=action_val,
        created_at=datetime.now(timezone.utc),
    )
    db.add(alert)
    await db.commit()
    await db.refresh(alert)
    return alert


async def list_alerts(
    db: AsyncSession,
    resolved: Optional[bool] = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[Sequence[Alert], int]:
    """
    List alerts with optional resolved status filter and pagination.
    Returns (items, total).
    """
    stmt = select(Alert)
    count_stmt = select(func.count()).select_from(Alert)

    if resolved is True:
        stmt = stmt.where(Alert.resolved_at.is_not(None))
        count_stmt = count_stmt.where(Alert.resolved_at.is_not(None))
    elif resolved is False:
        stmt = stmt.where(Alert.resolved_at.is_(None))
        count_stmt = count_stmt.where(Alert.resolved_at.is_(None))

    stmt = stmt.order_by(Alert.created_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    total_res = await db.execute(count_stmt)
    total = total_res.scalar_one()

    res = await db.execute(stmt)
    items = res.scalars().all()

    return items, total


async def resolve_alert(
    db: AsyncSession,
    alert_id: uuid.UUID,
) -> Optional[Alert]:
    """Mark an alert as resolved."""
    stmt = select(Alert).where(Alert.id == alert_id)
    res = await db.execute(stmt)
    alert = res.scalar_one_or_none()
    if alert is not None:
        alert.resolved_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(alert)
    return alert
