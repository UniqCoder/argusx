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
    Integer,
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
    # Which investigation this anchor/trace belongs to, when traced from a
    # case context — nullable because a wallet can be traced ad hoc with no
    # case selected. Lets a case's Evidence Trail show the real anchor/
    # trace/decision events for that specific investigation.
    case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("cases.id"), nullable=True,
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
    # ── Trace honesty fields ────────────────────────────────────────────────
    # Persisted (not just returned) so that GET /engine/trace/{id}, the PDF
    # report and the dashboard graph all describe the same trace with the same
    # caveats. max_hops above is what was REQUESTED; this is what was reached.
    depth_reached: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    # frontier_exhausted | node_budget | all_branches_dust
    termination_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    # The tainted seed actually used, and where it came from
    # ("reported_amount" or "observed_inflow"). Previously the seed was
    # hardcoded to 1.0 and therefore unrecorded and unauditable.
    seed_value: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    seed_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    # Onward branches deliberately not followed because their apportioned
    # value was at/below the dust threshold.
    pruned_branch_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pruned_branch_value: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    # The asset this trace followed, and how it was chosen. Taint is only
    # coherent within one asset.
    asset: Mapped[str | None] = mapped_column(String, nullable=True)
    asset_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    other_asset_branch_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Where this trace's transaction data came from: live | seeded_scenario |
    # mixed. Asserted by the engine from which explorer answered, so the
    # "seeded scenario" badge is server-side truth rather than a client-side
    # guess at an address prefix. See migration 0006.
    data_source: Mapped[str | None] = mapped_column(String, nullable=True)
    scenario_key: Mapped[str | None] = mapped_column(String, nullable=True)

    # ── Roles/clustering trace-level output (migration 0007) ────────────────
    # Wallets observed funding the anchor (the victim side — the BFS only
    # walks forward) and the wallet clusters detected in this trace. Stored as
    # JSON rather than normalised tables: both are a reading of one finished
    # trace, never queried independently of it, and re-deriving them from
    # scratch on every GET would let the persisted graph and the read-back
    # description drift apart.
    inbound_sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    clusters: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Laundering patterns detected + the path-risk breakdown. See
    # app/engine/typologies.py. JSON for the same reason as clusters above: a
    # reading of one finished trace, never queried independently of it.
    typologies: Mapped[list | None] = mapped_column(JSON, nullable=True)
    path_risk: Mapped[dict | None] = mapped_column(JSON, nullable=True)


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
    # VASP | MIXER_BOUNDARY | BRIDGE | DUST | DEPTH_LIMIT | NODE_LIMIT |
    # NO_OUTFLOW | EXPLORER_UNAVAILABLE | DILUTED_OUTFLOW | None (still frontier)
    terminal_kind: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_name: Mapped[str | None] = mapped_column(String, nullable=True)
    entity_jurisdiction: Mapped[str | None] = mapped_column(String, nullable=True)
    proof_path: Mapped[list] = mapped_column(JSON, nullable=False, default=list)  # ordered tx hashes
    first_tainted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    # The specific incoming edge that reached this node (None for the anchor
    # itself) — lets callers render the real branching graph, not a flat list.
    parent_address: Mapped[str | None] = mapped_column(String, nullable=True)
    tx_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    tx_amount: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    # Onward transfers from this address that were NOT followed, because after
    # haircut apportionment they carried value at/below the dust threshold.
    # Persisted so a sparse graph can always explain itself instead of looking
    # truncated.
    pruned_child_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pruned_child_value: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    other_asset_child_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ── Roles, clustering, cross-chain (migration 0007) ─────────────────────
    # A reading of the finished graph, computed once and persisted so
    # GET /engine/trace/{id} and the PDF report describe the same graph the
    # live trace showed — not a re-derivation that could drift.
    role: Mapped[str | None] = mapped_column(String, nullable=True)
    role_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_label: Mapped[str | None] = mapped_column(String, nullable=True)
    value_in: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    value_out: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    value_parked: Mapped[float | None] = mapped_column(Numeric(24, 8), nullable=True)
    # "ON_CHAIN" (default) or "CROSS_CHAIN_HEURISTIC" — see app/engine/crosschain.py.
    link_basis: Mapped[str | None] = mapped_column(String, nullable=True)
    link_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)
    link_detail: Mapped[str | None] = mapped_column(String, nullable=True)


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
