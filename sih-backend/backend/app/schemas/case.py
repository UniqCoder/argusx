"""app/schemas/case.py — Case schemas."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import CaseStatus


class CaseCreate(BaseModel):
    assigned_investigator: Optional[str] = None
    wallet_ids: Optional[List[UUID]] = Field(default_factory=list)
    initial_status: CaseStatus = CaseStatus.new


class CaseRead(BaseModel):
    id: UUID
    status: CaseStatus
    assigned_investigator: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CasePatch(BaseModel):
    status: Optional[CaseStatus] = None
    assigned_investigator: Optional[str] = None
