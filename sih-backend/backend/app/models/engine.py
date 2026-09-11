"""
app/models/engine.py — SQLAlchemy ORM for the ARGUS v2 provenance engine.

Five tables backing ARGUS-ENGINE-V2.md:
  - anchors            Layer 0 · ground-truth attestations (never system-generated)
  - traces             Layer 1 · one row per taint-propagation run
  - taint_nodes        Layer 1 · one row per address reached by a trace
  - evidence_ledger    Layer 5 · hash-chained, tamper-evident event log
  - decisions          Layer 5 · monitor/hold_for_review/block, DB-enforced guard

Uses the same postgresql.UUID/TIMESTAMP dialect types as the rest of app/models/
(these compile to generic equivalents on SQLite, which the test suite uses via
sqlite+aiosqlite — see app/tests/conftest.py). JSON is used instead of
postgresql.ARRAY for list-valued columns for the same cross-dialect reason.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Anchor(Base):
    """Layer 0 — nothing is 'bad' without one of these. See ARGUS-ENGINE-V2.md §Layer 0."""

    __tablename__ = "anchors"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    address: Mapped[str] = mapped_column(String, nullable=False)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    attestation_class: Mapped[str] = mapped_column(String(1), nullable=False)  # A | B | C
    attestation_type: Mapped[str] = mapped_column(String, nullable=False)
    source_ref: Mapped[str] = mapped_column(String, nullable=False)
    asserted_by: Mapped[str] = mapped_column(String, nullable=False)
    asserted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    victim_amount_inr: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    evidence_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    # Anti-feedback-loop guard (documented open risk in v1, closed here by construction):
    # an address our own system flags can never become an anchor. Anchors are
    # externally attested only — enforced in app/engine/anchors.py, mirrored here
    # so a direct DB write can't silently violate it either.
    system_generated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint("address", "chain", "source_ref", name="uq_anchor_addr_chain_source"),
        CheckConstraint("attestation_class IN ('A','B','C')", name="ck_anchor_attestation_class"),
        CheckConstraint(
            "system_generated = false",
            name="ck_anchor_never_system_generated",
        ),
    )


class Trace(Base):
    """Layer 1 — one row per taint-propagation run. See ARGUS-ENGINE-V2.md §Layer 1."""

    __tablename__ = "traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    anchor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("anchors.id"), nullable=False)
    method: Mapped[str] = mapped_column(String, nullable=False, server_default="haircut")
    dilution_floor: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False, server_default="0.005")
    max_hops: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="6")
    max_nodes: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="200")
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(),
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    node_count: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # SHA-256 over canonical (anchor params + result) — same inputs always
    # reproduce this exact hash. See app/engine/taint.py::_reproducible_hash.
    reproducible_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class TaintNode(Base):
    """Layer 1 output — every address the trace reached, with its proof path."""

    __tablename__ = "taint_nodes"

    trace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("traces.id"), primary_key=True,
    )
    address: Mapped[str] = mapped_column(String, primary_key=True)
    chain: Mapped[str] = mapped_column(String, primary_key=True)
    hop: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    taint_fraction: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    tainted_value: Mapped[float] = mapped_column(Numeric(24, 8), nullable=False)
    tainted_inr: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    # VASP | MIXER_BOUNDARY | BRIDGE | DUST | DEPTH_LIMIT | NODE_LIMIT | None (still frontier)
    terminal_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_name: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    proof_path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # ordered tx hashes
    first_tainted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class EvidenceLedgerEntry(Base):
    """
    Layer 5 — tamper-evident hash chain. entry_hash = SHA256(prev_hash ||
    canonical_json(payload) || occurred_at). See app/engine/ledger.py.
    """

    __tablename__ = "evidence_ledger"

    seq: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    event_type: Mapped[str] = mapped_column(String, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    actor: Mapped[str] = mapped_column(String, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(),
    )
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class Decision(Base):
    """
    Layer 5 — the three-tier action. The block_requires_anchor CHECK constraint
    is the §3 structural guarantee expressed in the database itself: even a bug
    in the service layer cannot persist an ML-only block. See
    app/engine/decision.py and app/tests/test_engine_decision.py.
    """

    __tablename__ = "decisions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    case_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    address: Mapped[str] = mapped_column(String, nullable=False)
    chain: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # monitor | hold_for_review | block
    basis_anchor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("anchors.id"), nullable=True)
    basis_trace_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("traces.id"), nullable=True)
    ml_contributed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(),
    )
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    released_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "action IN ('monitor','hold_for_review','block')",
            name="ck_decision_action",
        ),
        CheckConstraint(
            "action <> 'block' OR (basis_anchor_id IS NOT NULL AND basis_trace_id IS NOT NULL)",
            name="ck_block_requires_anchor",
        ),
    )
