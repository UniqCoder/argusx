"""app/schemas/alert.py — Alert schema."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel

from app.schemas.common import AlertAction, TriggeredBy


class AlertRead(BaseModel):
    id: UUID
    wallet_id: UUID
    case_id: Optional[UUID] = None
    triggered_by: TriggeredBy
    action: AlertAction
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = {"from_attributes": True}
