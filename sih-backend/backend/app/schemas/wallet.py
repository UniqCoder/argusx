"""app/schemas/wallet.py — Wallet, trace, and risk schemas."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Chain, EvidenceDirection, RiskTier


class WalletRead(BaseModel):
    id: UUID
    address: str
    chain: Chain
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_tier: Optional[RiskTier] = None
    vasp_identified: Optional[str] = None
    cluster_id: Optional[UUID] = None
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None

    model_config = {"from_attributes": True}


class Hop(BaseModel):
    from_address: str
    to_address: str
    tx_hash: str
    amount: float
    chain: Chain
    timestamp: datetime


class TraceResponse(BaseModel):
    wallet: WalletRead
    path: List[Hop]
    nearest_vasp: Optional[str] = None
    hops_count: int
    traced_at: datetime


class RiskEvidence(BaseModel):
    feature_name: str
    contribution: float
    direction: EvidenceDirection


class RiskResponse(BaseModel):
    risk_score: float = Field(..., ge=0.0, le=1.0)
    risk_tier: RiskTier
    evidence: List[RiskEvidence]
