"""
app/schemas/engine.py — Pydantic request/response models for the ARGUS v2
provenance engine (anchors, taint trace, decisions, ledger).

These are additive — no existing schema (wallet/risk/case/alert/...) is
changed, so the existing frontend API client and its typed responses are
unaffected.
"""
import re
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Chain

# ── Per-chain address shape validation (mirrors src/lib/address.ts) ──────────
# Malformed anchors used to be accepted and only fail later, inside the taint
# engine's real explorer calls — wasting rate-limited explorer quota and
# surfacing as a confusing failed trace. Validating the shape here makes the
# API 422 at the boundary. Checksums are NOT verified (EIP-55 / base58
# checksum would reject legitimately-typed addresses and explorers treat
# addresses case-insensitively); this is a shape gate, not an ownership proof.
_EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
_BTC_BASE58_RE = re.compile(r"^[13][1-9A-HJ-NP-Za-km-z]{25,39}$")
_BTC_BECH32_RE = re.compile(r"^bc1[023456789ac-hj-np-z]{11,71}$")
_TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
_EVM_TX_HASH_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
_BARE_TX_HASH_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def is_valid_anchor_shape(chain: str, address: str) -> bool:
    """True if `address` looks like a real address (or tx hash) on `chain`."""
    if chain in ("ETH", "BSC"):
        return bool(_EVM_ADDRESS_RE.match(address) or _EVM_TX_HASH_RE.match(address))
    if chain == "BTC":
        return bool(_BTC_BASE58_RE.match(address) or _BTC_BECH32_RE.match(address))
    if chain == "TRON":
        return bool(_TRON_ADDRESS_RE.match(address) or _BARE_TX_HASH_RE.match(address))
    return True  # unknown/other chains: no shape gate yet


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
    # This address's own recent transactions include no outgoing transfers —
    # a real, correct result (a contract, a receive-only wallet, or activity
    # older than the fetched window), not a failure. Previously taint.py
    # used the raw string "NO_OUTFLOW" here for non-root nodes without it
    # being a valid enum member, which would have raised a validation error
    # the first real trace that hit this branch.
    NO_OUTFLOW = "NO_OUTFLOW"
    # The blockchain explorer could not be reached for this node (timeout /
    # 5xx / rate-limit). This is an infrastructure condition, NOT an honest
    # dead-end: previously it was recorded as DEPTH_LIMIT, which misreported
    # "we stopped tracing because the trace got too deep" when the truth was
    # "we could not fetch data at all". Frontend renders this as a retryable
    # state, not a completed trace.
    EXPLORER_UNAVAILABLE = "EXPLORER_UNAVAILABLE"
    # This address DOES have outgoing transfers, but after haircut
    # apportionment every one of them carried less tainted value than the dust
    # threshold, so none was worth following. Before this existed such a node
    # was returned with terminal_kind=None — indistinguishable from a node the
    # trace simply had not got to yet, which is why traces looked like they
    # "just stopped" for no stated reason. The pruned branches are counted on
    # the node (`pruned_child_count`/`pruned_child_value`) so the UI can say
    # how much money was set aside and why, instead of silently dropping it.
    DILUTED_OUTFLOW = "DILUTED_OUTFLOW"


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
    # Which investigation this belongs to, when traced from a case context.
    case_id: Optional[UUID] = None

    @model_validator(mode="after")
    def _validate_address_shape(self) -> "AnchorCreate":
        addr = self.address.strip()
        if not is_valid_anchor_shape(self.chain.value, addr):
            raise ValueError(
                f"'{addr[:24]}…' does not look like a valid {self.chain.value} "
                "address or transaction hash."
            )
        return self


class AnchorRead(BaseModel):
    id: UUID
    case_id: Optional[UUID] = None
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
    # The real amount known to have been stolen, in the chain's native unit,
    # when the complaint states one. Left unset the engine seeds from the
    # anchor address's observed inflow instead of inventing a value.
    seed_value: Optional[Decimal] = Field(default=None, gt=0)


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
    # Onward transfers from this address that were NOT followed because their
    # apportioned tainted value was at or below the dust threshold. Recorded
    # so a sparse-looking graph can explain itself ("4 branches holding
    # 0.00031 ETH were below the dust floor") rather than appearing truncated.
    pruned_child_count: int = 0
    pruned_child_value: Decimal = Decimal("0")
    # Onward transfers in a different asset than the one being traced. Real
    # money movements that are simply out of this run's asset scope — counted
    # separately so they are never mistaken for dust.
    other_asset_child_count: int = 0
    # Real on-chain timestamp of the transaction that reached this node
    # (None for the anchor). Already computed and persisted — see
    # app/engine/taint.py's TaintedNode — just not returned until now. Lets
    # the frontend do an honest chronological replay instead of an
    # arbitrary progress bar.
    first_tainted_at: Optional[datetime] = None

    # ── Roles, clustering, cross-chain (app/engine/roles.py, clustering.py,
    # crosschain.py) — a reading of the finished graph, not part of the taint
    # arithmetic. Optional because they are absent on nodes reported mid-stream
    # (roles are computed once the whole graph is known) and on rows persisted
    # before this existed.
    role: Optional[str] = None
    role_basis: Optional[str] = None
    description: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None
    value_in: Decimal = Decimal("0")
    value_out: Decimal = Decimal("0")
    value_parked: Decimal = Decimal("0")
    # How the INBOUND edge to this node was established. "ON_CHAIN" (default)
    # for a real signed transaction; "CROSS_CHAIN_HEURISTIC" for a bridge
    # deposit matched to a same-value release on another chain — a
    # correlation, not a proof, and rendered differently for that reason.
    link_basis: str = "ON_CHAIN"
    link_confidence: Optional[float] = None
    link_detail: Optional[str] = None

    model_config = {"from_attributes": True}


class InboundSourceRead(BaseModel):
    """A wallet observed paying INTO the anchor. See app/engine/taint.py."""
    address: str
    chain: Chain
    amount: Decimal
    asset: str
    tx_hash: str
    timestamp: Optional[datetime] = None


class ClusterMember(BaseModel):
    address: str
    chain: Chain


class ClusterRead(BaseModel):
    id: str
    label: str
    basis: str
    members: list[ClusterMember]


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
    # ── Trace honesty fields ────────────────────────────────────────────────
    # How deep the trace actually got, versus how deep it was asked to go.
    # Without this the UI could only report the requested depth, so a trace
    # asked for 8 hops that genuinely reached 3 looked like a successful
    # 8-hop trace. `max_hops` above is the request; this is the outcome.
    depth_reached: int
    # Why propagation stopped, in the engine's own words. One of:
    #   "frontier_exhausted" — every reachable branch ended in a real terminal
    #   "node_budget"        — max_nodes reached with money still untraced
    #   "all_branches_dust"  — remaining branches were all below the floor
    termination_reason: str
    # What the tainted-value seed was, and where it came from. The seed used
    # to be hardcoded to 1.0 native unit regardless of the complaint, which
    # made every downstream taint_fraction arithmetic on an invented number.
    seed_value: Decimal
    # "reported_amount" (the complaint stated one) or "observed_inflow"
    # (no amount known, so all funds observed arriving at the anchor are
    # treated as tainted — the conservative forensic default).
    seed_basis: str
    # Totals for branches deliberately not followed (see pruned_child_* above).
    pruned_branch_count: int
    pruned_branch_value: Decimal
    # The single asset this trace followed (e.g. "USDT", "ETH", "BTC") and how
    # it was chosen ("dominant_inflow" / "dominant_outflow" / "no_activity").
    # Taint fractions are only meaningful within one asset, and the UI needs
    # this to label amounts correctly — it previously printed the CHAIN as the
    # ticker, so a USDT transfer on TRON rendered as "691.53 TRON".
    asset: str
    asset_basis: str
    other_asset_branch_count: int
    # ── Data provenance ─────────────────────────────────────────────────────
    # Which explorer actually answered for the addresses this trace walked:
    #   "live"            a public blockchain explorer
    #   "seeded_scenario" the seeded-scenario fixture (app/services/scenarios/)
    #   "mixed"           both
    # The UI must show a clearly-labelled badge for anything that is not
    # "live". This is asserted here, server-side, precisely so that a client
    # cannot decide it: a seeded case must never be able to look like a live
    # one on any screen, in any export, or in the PDF report.
    data_source: str = "live"
    scenario_key: Optional[str] = None
    # Wallets observed funding the anchor — the victim side, which the BFS
    # (forward-only by construction) cannot otherwise show.
    inbound_sources: list[InboundSourceRead] = []
    # Groups of wallets one operator plausibly controls. See clustering.py.
    clusters: list[ClusterRead] = []
    # Laundering patterns this trace exhibits, and a plain-language path-risk
    # breakdown. Explanation only -- never a decision input. See
    # app/engine/typologies.py and IMPROVEMENTS_PLANNED.md's explicit
    # rejection of a fused confidence score that could drive a block.
    typologies: list[dict] = []
    path_risk: dict = {}


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
