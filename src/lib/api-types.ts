// ============================================================
// ARGUS — API Types
// Mirrors contracts/openapi.yaml exactly.
// Never extend enums inline — update entities.md first.
// ============================================================

// Wire values only — these must match app/schemas/common.py exactly. Display
// names live in src/lib/chains.ts; do not put "Polygon" (or any other label)
// in this union, which is what previously forced `as` casts at every boundary.
//
// POLYGON and BSC are valid chains but are NOT independently traceable: the
// engine has no live explorer for either, so they appear only as the
// destination side of a cross-chain hand-off. See TRACEABLE_CHAINS.
export type Chain = "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";
export type RiskTier = "critical" | "high" | "medium" | "low" | "unknown";
export type CaseStatus =
  "new" | "investigating" | "escalated_to_vasp" | "frozen" | "closed";
export type AlertAction = "allow" | "hold" | "block";
export type SourcePlatform = "ncrp" | "sahyog" | "manual";
export type TriggeredBy = "check_wallet_hook" | "registry_refresh" | "manual";
export type EvidenceDirection = "increases_risk" | "decreases_risk";
export type Role = "admin" | "investigator" | "compliance_viewer";

// ── Error envelope (all failures) ─────────────────────────────────────────
export interface ApiError {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}

// ── Pagination ─────────────────────────────────────────────────────────────
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

// ── Core entities ──────────────────────────────────────────────────────────
export interface RiskEvidence {
  feature_name: string;
  contribution: number;
  direction: EvidenceDirection;
  // Only populated for non-ML evidence (e.g. a sanctions-list match) — the
  // designation text the backend already computed, not something the
  // frontend should try to re-derive from feature_name.
  detail?: string | null;
}

export interface Complaint {
  id: string;
  ncrp_ref?: string | null;
  source_platform: SourcePlatform;
  narrative_text?: string | null;
  fraud_typology?: string | null;
  amount_lost?: number | null;
  filed_at: string;
  state?: string | null;
  district?: string | null;
  created_at: string;
}

export interface ExtractedEntities {
  suspect_names: string[];
  amounts_mentioned: { amount: number; currency: string }[];
  crypto_addresses: { address: string; chain: string }[];
  dates_mentioned: string[];
  fraud_typology?: string | null;
  summary?: string | null;
  extractor_used?: string | null;
  latency_ms?: number | null;
}

export interface ComplaintDetail extends Complaint {
  extracted_entities?: ExtractedEntities | null;
}

export interface CaseWallet {
  id: string;
  address: string;
  chain: string;
  risk_score?: number | null;
  risk_tier?: RiskTier | null;
  first_seen?: string | null;
  last_seen?: string | null;
}

export interface Case {
  id: string;
  status: CaseStatus;
  assigned_investigator?: string | null;
  opened_at: string;
  closed_at?: string | null;
  wallets: CaseWallet[];
}

export interface Alert {
  id: string;
  wallet_id: string;
  case_id?: string | null;
  triggered_by: TriggeredBy;
  action: AlertAction;
  created_at: string;
  resolved_at?: string | null;
}

// ── Auth ───────────────────────────────────────────────────────────────────
export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  role: Role;
}

export interface RefreshResponse {
  access_token: string;
}

// ── Decimal wire format ─────────────────────────────────────────────────────
// The backend's numeric forensic fields are Python `Decimal`, and Pydantic
// serialises Decimal as a JSON **string** to avoid float precision loss
// (`"930.125872"`, not `930.125872`). Integer fields (hop, counts) come back as
// real JSON numbers.
//
// These fields were previously typed as plain `number`, which was simply
// untrue at runtime. Nothing caught it because the only consumer interpolated
// them into template strings (`${n.tx_amount} ${n.chain}`), where a string
// behaves identically. The first piece of code to do real arithmetic on one
// crashed with "amount.toFixed is not a function".
//
// Typed honestly as `Decimal` below. Anything doing maths on these must run
// them through `toNum()` (src/lib/decimal.ts) rather than assuming.
export type Decimal = number | string;

// ── Wallet endpoints ───────────────────────────────────────────────────────
export interface RiskResponse {
  // NULLABLE, and that is load-bearing. The backend returns null (with
  // risk_tier "unknown") when a wallet genuinely cannot be scored — ML
  // artifacts absent, or an address the model has no basis for. This field was
  // typed as a plain `number`, so the frontend did `Math.round(null * 100)`
  // and rendered a perfectly honest "we don't know" as **0/100**, i.e. as a
  // verified-clean wallet. Unknown is not low risk.
  risk_score: number | null;
  risk_tier: RiskTier;
  evidence: RiskEvidence[];
}

// ── Provenance engine (v2) — anchors + taint-propagation trace ─────────────
export type AttestationClass = "A" | "B" | "C";
export type AttestationType =
  | "LEGAL_COMPLAINT"
  | "SOVEREIGN_DESIGNATION"
  | "PUBLIC_ATTRIBUTED_REPORT"
  | "INVESTIGATOR_ASSERTED";
export type TaintMethod = "haircut" | "poison" | "fifo";
export type TerminalKind =
  | "VASP"
  | "MIXER_BOUNDARY"
  | "BRIDGE"
  | "DUST"
  | "DEPTH_LIMIT"
  | "NODE_LIMIT"
  | "NO_OUTFLOW"
  // Explorer unreachable for this node (timeout/5xx/rate-limit) — retryable
  // infrastructure condition, NOT an honest dead-end (see app/engine/taint.py).
  | "EXPLORER_UNAVAILABLE"
  // This address HAS outgoing transfers, but every one of them carried
  // at/below-dust tainted value after apportionment, so none was worth
  // following. Distinct from a node the trace simply hadn't reached yet —
  // which is what it was indistinguishable from before.
  | "DILUTED_OUTFLOW";
export type DecisionAction = "monitor" | "hold_for_review" | "block";

export interface AnchorCreate {
  address: string;
  chain: Chain;
  attestation_class: AttestationClass;
  attestation_type: AttestationType;
  source_ref: string;
  asserted_by: string;
  victim_amount_inr?: number | null;
  evidence_uri?: string | null;
  case_id?: string | null;
}

export interface AnchorRead {
  id: string;
  case_id?: string | null;
  address: string;
  chain: Chain;
  attestation_class: AttestationClass;
  attestation_type: string;
  source_ref: string;
  asserted_by: string;
  asserted_at: string;
  victim_amount_inr?: number | null;
  evidence_uri?: string | null;
  created_at: string;
}

export interface EngineTraceRequest {
  anchor_id: string;
  method?: TaintMethod;
  max_hops?: number;
  max_nodes?: number;
  dilution_floor?: number;
}

export interface TaintNodeRead {
  address: string;
  chain: Chain;
  hop: number;
  taint_fraction: Decimal;
  tainted_value: Decimal;
  tainted_inr?: Decimal | null;
  terminal_kind?: TerminalKind | null;
  entity_name?: string | null;
  entity_jurisdiction?: string | null;
  proof_path: string[];
  still_active: boolean;
  parent_address?: string | null;
  tx_hash?: string | null;
  tx_amount?: Decimal | null;
  first_tainted_at?: string | null;
  // Onward transfers from this address the engine deliberately did NOT follow
  // because, after haircut apportionment, they carried value at/below the dust
  // floor. Surfaced so a sparse graph can explain itself instead of looking
  // truncated.
  pruned_child_count?: number;
  pruned_child_value?: Decimal;
  // Onward transfers in a DIFFERENT asset than the one being traced — real
  // money movements outside this run's asset scope, never dust.
  other_asset_child_count?: number;
}

export interface EngineTraceResult {
  trace_id: string;
  anchor: AnchorRead;
  method: TaintMethod;
  dilution_floor: Decimal;
  max_hops: number;
  node_count: number;
  nodes: TaintNodeRead[];
  terminals: TaintNodeRead[];
  unattributed_residual: Decimal;
  terminated_at_mixer: Decimal;
  reproducible_hash: string;
  completed_at: string;
  // ── Trace honesty fields ──────────────────────────────────────────────────
  // `max_hops` above is what was REQUESTED; this is what was actually reached.
  depth_reached: number;
  // Why propagation stopped, in the engine's own words:
  // "frontier_exhausted" | "node_budget" | "all_branches_dust" | "unrecorded"
  termination_reason: string;
  // The tainted seed used, and its provenance ("reported_amount" |
  // "observed_inflow"). The seed used to be hardcoded to 1.0 native unit, so
  // every taint fraction was arithmetic on an invented number.
  seed_value: Decimal;
  seed_basis: string;
  pruned_branch_count: number;
  pruned_branch_value: Decimal;
  // The single asset this trace followed (e.g. "USDT") and how it was chosen.
  // Needed to label amounts correctly — the UI used to print the CHAIN as the
  // ticker, rendering a USDT transfer as "691.53 TRON".
  asset: string;
  asset_basis: string;
  other_asset_branch_count: number;
  // ── Data provenance ───────────────────────────────────────────────────────
  // Which explorer actually answered for the addresses this trace walked.
  // Asserted by the ENGINE, never inferred here: a seeded scenario must not be
  // able to look like a live trace on any screen. Anything other than "live"
  // must render a visible badge.
  data_source: "live" | "seeded_scenario" | "mixed";
  scenario_key: string | null;
}

// ── Seeded scenarios ───────────────────────────────────────────────────────
// Mirrors app/schemas/scenario.py. These describe seeded investigation cases
// that run through the real engine over a fixture explorer — they are NOT a
// client-side fixture, and the UI must not carry its own copy of them.
export interface ScenarioComplaintRead {
  ncrp_ref: string;
  source_platform: SourcePlatform;
  state: string;
  district: string;
  fraud_typology: string;
  amount_lost_inr: number;
}

export interface ScenarioRead {
  key: string;
  title: string;
  subtitle: string;
  typology: string;
  headline: string;
  demonstrates: string[];
  anchor_address: string;
  anchor_chain: Chain;
  asset: string;
  chains: Chain[];
  victim_amount_inr: number;
  complaint_count: number;
  transaction_count: number;
  complaints: ScenarioComplaintRead[];
  // Null when the scenario is defined but has not been seeded into this
  // database — the UI says "run the reset script", it does not pretend.
  case_id: string | null;
}

export interface ScenarioListResponse {
  seeded: boolean;
  scenarios: ScenarioRead[];
}

// ── Complaint ingestion ─────────────────────────────────────────────────────
// Mirrors app/schemas/complaint.py.
export interface ComplaintWalletIn {
  address: string;
  chain: Chain;
}

export interface ComplaintCreate {
  ncrp_ref?: string | null;
  source_platform: SourcePlatform;
  narrative_text?: string | null;
  fraud_typology?: string | null;
  amount_lost?: number | null;
  filed_at: string;
  state?: string | null;
  district?: string | null;
  // The wallet(s) the complainant names. THIS is the write path cross-victim
  // correlation depends on — without it, POST /api/v1/correlate can never
  // find a linked complaint for a real (non-seeded) wallet.
  wallets?: ComplaintWalletIn[];
}

// ── Deposit check ──────────────────────────────────────────────────────────
export interface DepositCheckRequest {
  address: string;
  chain: Chain;
  amount: number;
}

export interface DepositCheckResponse {
  risk_score: number;
  action: AlertAction;
  case_ref?: string | null;
  // The recorded basis for a flagged entry, when one exists. Deposit Watch
  // shows this instead of asking the investigator to trust a bare number.
  reason?: string | null;
  // The SAME risk_tier Risk Intelligence shows for this wallet — color the
  // verdict off this, never re-derive thresholds from the raw score.
  risk_tier?: string | null;
}

export interface DepositDecisionRequest {
  address: string;
  chain: Chain;
  risk_score: number;
  action: AlertAction;
  decision: "allowed" | "flagged";
  // An opaque registry label — display only, never a real case link.
  case_ref?: string | null;
  // The investigator's real active case UUID, when one exists. This is
  // what actually links the ledger entry to a case's Evidence Trail.
  case_id?: string | null;
  note?: string | null;
}

export interface DepositDecisionResponse {
  recorded: boolean;
}

// ── Correlation ────────────────────────────────────────────────────────────
export interface CorrelateRequest {
  wallet_id?: string;
  address?: string;
  chain?: Chain;
}

export interface CorrelateResponse {
  correlation_score: number;
  linked_complaints: Complaint[];
  distinct_geographies: number;
  total_amount: number;
}

// ── Cases ──────────────────────────────────────────────────────────────────
export interface CaseCreate {
  assigned_investigator?: string | null;
  wallet_ids?: string[];
  initial_status?: CaseStatus;
}

export interface CasePatch {
  status?: CaseStatus;
  assigned_investigator?: string | null;
}

// ── Evidence Trail — real audit-log + forensic-ledger events for a case ────
export interface EvidenceEvent {
  source: "audit" | "ledger";
  event_type: string;
  actor?: string | null;
  occurred_at: string;
  details: Record<string, unknown>;
}

// ── Health ─────────────────────────────────────────────────────────────────
export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  services?: {
    postgres: "ok" | "degraded" | "down";
    neo4j: "ok" | "degraded" | "down";
    redis: "ok" | "degraded" | "down";
  };
}
