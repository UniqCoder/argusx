"""app/schemas/wallet.py — Wallet, trace, and risk schemas."""
from datetime import datetime
from typing import List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Chain, EvidenceDirection, RiskTier


class OsintEvidence(BaseModel):
    """Structured OSINT hit surfaced alongside ML evidence in /risk.

    Sources: ransomwhe.re (ransomware families), Bitcoin Abuse (abuse reports).
    Each hit is a structured, source-attributed datum — not free text.
    """
    source: str
    category: str
    report_date: Optional[str] = None
    detail: Optional[str] = None
    reference_url: Optional[str] = None


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
    detail: Optional[str] = None


class RiskResponse(BaseModel):
    risk_score: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk_tier: RiskTier = RiskTier.unknown
    risk_source: Literal["ml_model", "sanctions_override"] = "ml_model"
    evidence: List[RiskEvidence] = Field(default_factory=list)
    osint: List[OsintEvidence] = Field(default_factory=list)
