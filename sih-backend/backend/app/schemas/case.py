"""app/schemas/case.py — Case schemas."""
from datetime import datetime
from typing import Any, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import CaseStatus


class CaseCreate(BaseModel):
    assigned_investigator: Optional[str] = None
    wallet_ids: Optional[List[UUID]] = Field(default_factory=list)
    initial_status: CaseStatus = CaseStatus.new


class CaseWalletRead(BaseModel):
    id: UUID
    address: str
    chain: str
    risk_score: Optional[float] = None
    risk_tier: Optional[str] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}


class CaseRead(BaseModel):
    id: UUID
    status: CaseStatus
    assigned_investigator: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None
    wallets: List[CaseWalletRead] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class CasePatch(BaseModel):
    status: Optional[CaseStatus] = None
    assigned_investigator: Optional[str] = None


class EvidenceEvent(BaseModel):
    """One real, already-recorded event for a case's Evidence Trail.

    Two real sources, merged and sorted by when they actually happened:
    the immutable audit log (view/update/export actions — app/models/audit.py)
    and the tamper-evident forensic-engine ledger (anchor/trace/decision
    events — app/models/engine.py's EvidenceLedgerEntry). Nothing here is
    synthesized for this endpoint; both tables already existed and were
    already being written to.
    """

    source: Literal["audit", "ledger"]
    event_type: str
    actor: Optional[str] = None
    occurred_at: datetime
    details: dict[str, Any] = Field(default_factory=dict)
