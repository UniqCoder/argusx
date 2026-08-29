"""
app/services/audit_service.py — Immutable audit logging service.

Records investigator actions (view, export, update) into PostgreSQL audit_log table.
"""
from datetime import datetime, timezone
import logging
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)


async def record_audit_log(
    db: AsyncSession,
    action: str,
    entity: str,
    entity_id: Optional[uuid.UUID] = None,
    actor: Optional[str] = None,
) -> AuditLog:
    """Write an immutable audit log entry."""
    entry = AuditLog(
        actor=actor or "system",
        action=action,
        entity=entity,
        entity_id=entity_id,
        timestamp=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    logger.info("audit_log_recorded", extra={"actor": actor, "action": action, "entity": entity, "entity_id": str(entity_id)})
    return entry


async def get_audit_logs_for_entity(
    db: AsyncSession,
    entity: str,
    entity_id: uuid.UUID,
) -> list[AuditLog]:
    """Retrieve audit trail for a specific entity."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.entity == entity, AuditLog.entity_id == entity_id)
        .order_by(AuditLog.timestamp.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
