// ============================================================
// ARGUS — API Types
// Mirrors contracts/openapi.yaml exactly.
// Never extend enums inline — update entities.md first.
// ============================================================

export type Chain = "BTC" | "ETH" | "TRON" | "BSC";
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

// ── Wallet endpoints ───────────────────────────────────────────────────────
export interface RiskResponse {
  risk_score: number;
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
  | "NODE_LIMIT";
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
}

export interface AnchorRead {
  id: string;
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
  taint_fraction: number;
  tainted_value: number;
  tainted_inr?: number | null;
  terminal_kind?: TerminalKind | null;
  entity_name?: string | null;
  entity_jurisdiction?: string | null;
  proof_path: string[];
  still_active: boolean;
  parent_address?: string | null;
  tx_hash?: string | null;
  tx_amount?: number | null;
}

export interface EngineTraceResult {
  trace_id: string;
  anchor: AnchorRead;
  method: TaintMethod;
  dilution_floor: number;
  max_hops: number;
  node_count: number;
  nodes: TaintNodeRead[];
  terminals: TaintNodeRead[];
  unattributed_residual: number;
  terminated_at_mixer: number;
  reproducible_hash: string;
  completed_at: string;
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
