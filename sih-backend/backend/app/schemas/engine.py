"""
app/schemas/engine.py — Pydantic request/response models for the ARGUS v2
provenance engine (anchors, taint trace, decisions, ledger).

These are additive — no existing schema (wallet/risk/case/alert/...) is
changed, so the existing frontend API client and its typed responses are
unaffected.
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Chain


class AttestationClass(str, Enum):
    A = "A"  # legally attested / sovereign — NCRP complaint, FIR, OFAC SDN
    B = "B"  # publicly attributed report — ransomwhe.re, Chainabuse, BitcoinAbuse
    C = "C"  # investigator hypothesis — analyst-asserted, never justifies a block


class AttestationType(str, Enum):
    LEGAL_COMPLAINT = "LEGAL_COMPLAINT"
    SOVEREIGN_DESIGNATION = "SOVEREIGN_DESIGNATION"
    PUBLIC_ATTRIBUTED_REPORT = "PUBLIC_ATTRIBUTED_REPORT"
    INVESTIGATOR_ASSERTED = "INVESTIGATOR_ASSERTED"


class TaintMethod(str, Enum):
    haircut = "haircut"
    poison = "poison"
    fifo = "fifo"


class TerminalKind(str, Enum):
    VASP = "VASP"
    MIXER_BOUNDARY = "MIXER_BOUNDARY"
    BRIDGE = "BRIDGE"
    DUST = "DUST"
    DEPTH_LIMIT = "DEPTH_LIMIT"
    NODE_LIMIT = "NODE_LIMIT"


class DecisionAction(str, Enum):
    monitor = "monitor"
    hold_for_review = "hold_for_review"
    block = "block"


# ── Anchors (Layer 0) ──────────────────────────────────────────────────────────

class AnchorCreate(BaseModel):
    address: str = Field(..., min_length=1, max_length=128)
    chain: Chain
    attestation_class: AttestationClass
    attestation_type: AttestationType
    source_ref: str = Field(..., min_length=1, max_length=255)
    asserted_by: str = Field(..., min_length=1, max_length=255)
    asserted_at: Optional[datetime] = None
    victim_amount_inr: Optional[Decimal] = Field(default=None, ge=0)
    evidence_uri: Optional[str] = None


class AnchorRead(BaseModel):
    id: UUID
    address: str
    chain: Chain
    attestation_class: AttestationClass
    attestation_type: str
    source_ref: str
    asserted_by: str
    asserted_at: datetime
    victim_amount_inr: Optional[Decimal] = None
    evidence_uri: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Trace (Layer 1) ────────────────────────────────────────────────────────────

class TraceRequest(BaseModel):
    anchor_id: UUID
    method: TaintMethod = TaintMethod.haircut
    max_hops: int = Field(default=6, ge=1, le=12)
    max_nodes: int = Field(default=60, ge=1, le=500)
    dilution_floor: Decimal = Field(default=Decimal("0.005"), ge=0, le=1)


class TaintNodeRead(BaseModel):
    address: str
    chain: Chain
    hop: int
    taint_fraction: Decimal
    tainted_value: Decimal
    tainted_inr: Optional[Decimal] = None
    terminal_kind: Optional[TerminalKind] = None
    entity_name: Optional[str] = None
    entity_jurisdiction: Optional[str] = None
    proof_path: list[str]
    still_active: bool
    # The specific incoming edge that reached this node — None only for the
    # anchor itself (hop 0). Lets the frontend render the real branching
    # graph (parent -> child edges) instead of a flat hop list.
    parent_address: Optional[str] = None
    tx_hash: Optional[str] = None
    tx_amount: Optional[Decimal] = None

    model_config = {"from_attributes": True}


class TraceResult(BaseModel):
    trace_id: UUID
    anchor: AnchorRead
    method: TaintMethod
    dilution_floor: Decimal
    max_hops: int
    node_count: int
    nodes: list[TaintNodeRead]
    terminals: list[TaintNodeRead]
    unattributed_residual: Decimal
    terminated_at_mixer: Decimal
    reproducible_hash: str
    completed_at: datetime


# ── Decisions (Layer 5) ────────────────────────────────────────────────────────

class DecisionRead(BaseModel):
    id: UUID
    address: str
    chain: Chain
    action: DecisionAction
    basis_anchor_id: Optional[UUID] = None
    basis_trace_id: Optional[UUID] = None
    ml_contributed: bool
    reasoning: str
    decided_at: datetime
    expires_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# ── Ledger (Layer 5) ───────────────────────────────────────────────────────────

class LedgerVerifyResponse(BaseModel):
    case_id: Optional[UUID] = None
    entries_checked: int
    intact: bool
    broken_at_seq: Optional[int] = None
    merkle_root: Optional[str] = None
