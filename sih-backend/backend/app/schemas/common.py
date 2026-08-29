"""
app/schemas/common.py — Shared schemas used by every endpoint.

These mirror the openapi.yaml ErrorEnvelope, PaginationMeta, and
the closed enum definitions from contracts/entities.md.
"""
from enum import Enum
from typing import Any, Generic, List, TypeVar

from pydantic import BaseModel, Field


# ── Closed enums — must match contracts/entities.md exactly ──────────────────
# Rules §7: never invent a new value inline on either side.

class RiskTier(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class CaseStatus(str, Enum):
    new = "new"
    investigating = "investigating"
    escalated_to_vasp = "escalated_to_vasp"
    frozen = "frozen"
    closed = "closed"


class AlertAction(str, Enum):
    allow = "allow"
    hold = "hold"
    block = "block"


class Chain(str, Enum):
    BTC = "BTC"
    ETH = "ETH"
    TRON = "TRON"
    BSC = "BSC"


class SourcePlatform(str, Enum):
    ncrp = "ncrp"
    sahyog = "sahyog"
    manual = "manual"


class TriggeredBy(str, Enum):
    check_wallet_hook = "check_wallet_hook"
    registry_refresh = "registry_refresh"
    manual = "manual"


class EvidenceDirection(str, Enum):
    increases_risk = "increases_risk"
    decreases_risk = "decreases_risk"


class UserRole(str, Enum):
    admin = "admin"
    investigator = "investigator"
    compliance_viewer = "compliance_viewer"


# ── Error envelope ────────────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# ── Pagination ────────────────────────────────────────────────────────────────

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
