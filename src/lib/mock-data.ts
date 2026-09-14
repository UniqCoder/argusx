// ============================================================
// ARGUS — Shared UI type definitions
//
// This file used to also hold MOCK_* sample data. That data has been
// removed: it was blended into real API results (not just used as an
// offline fallback), which meant genuine backend responses — including
// real empty results — could get silently replaced by fabricated
// cases/alerts/trace graphs/risk signals. See git history for the
// removed constants if you need sample data for a real test fixture or
// an explicitly-labeled demo mode — production code must never import
// mock data as a runtime fallback.
// ============================================================

// --- Cases ---
export type CaseStatus =
  | "live-trace"
  | "network-signal"
  | "vasp-identified"
  | "critical"
  | "evidence-ready"
  | "closed";
export type Blockchain = "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";
export type FraudType =
  | "Investment Scam"
  | "Task Fraud"
  | "Ransomware"
  | "Sextortion"
  | "Rug Pull"
  | "Phishing"
  | "NFT Fraud"
  | "Unclassified";

export interface InvestigationCase {
  id: string;
  // The real backend case UUID — required for any getCase()/getCaseReport()
  // call. `id` above is a cosmetic display label; this is the real key.
  rawId: string;
  // A real complaint's fraud_typology is a free string from NCRP categories
  // (e.g. "investment_fraud"), not this curated display-cased set — widened
  // from FraudType so real backend data never needs a lossy remap to fit a
  // fixed list designed for an earlier hardcoded-mock version of this page.
  fraudType: string;
  blockchain: Blockchain;
  reportedWallet: string;
  traceStatus: CaseStatus;
  networkSignal: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  // null when the linked wallet has never been scored — genuinely different
  // from a real 0, and must never be coerced into one.
  riskScore: number | null;
  // The backend's own tier string ("critical"/"high"/"medium"/"low"/
  // "unknown") — color must always come from THIS, never re-derived from
  // riskScore with a second set of thresholds that can disagree with the
  // backend's 0.30/0.60/0.85 boundaries.
  riskTier: string | null;
  victimCount: number;
  lastActivity: string;
  description: string;
}

// --- Intelligence Feed Events ---
export type EventSeverity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "INFO";

export interface IntelEvent {
  id: string;
  severity: EventSeverity;
  type: string;
  message: string;
  caseId: string;
  wallet?: string;
  timestamp: string;
  read: boolean;
}

// --- Trace Graph ---
export type NodeType =
  "victim" | "reported" | "intermediate" | "bridge" | "mixer" | "exchange";

export interface TraceNode {
  id: string;
  type: NodeType;
  label: string;
  address: string;
  blockchain: Blockchain;
  // Per-node risk isn't computed by the backend trace endpoint (only a
  // whole-wallet score exists, fetched separately) — left undefined rather
  // than fabricated. Populated only where a real value exists.
  riskScore?: number;
  resolved: boolean;
  amount?: string;
  // Real on-chain timestamp of the transaction that reached this node
  // (absent for the root/searched wallet). Drives chronological replay
  // ordering — not decoration.
  firstTaintedAt?: string;
  // Real terminal classification from the backend (VASP/MIXER_BOUNDARY/
  // BRIDGE/DUST/DEPTH_LIMIT/NODE_LIMIT/NO_OUTFLOW/DILUTED_OUTFLOW/
  // EXPLORER_UNAVAILABLE), when this node is one.
  terminalKind?: string;
  // Hop distance from the traced (root) wallet. Real, from the engine.
  hop?: number;
  // Real entity attribution from the curated registries (e.g. "Binance"),
  // only where one genuinely matched.
  entity?: string;
  // Branches the engine deliberately did not follow from this node, and why.
  // Lets a sparse node say "4 onward transfers were below the dust floor"
  // rather than just looking like a dead end.
  prunedChildCount?: number;
  prunedChildValue?: number;
  otherAssetChildCount?: number;
  // The investigation target — decoupled from `hop === 0` so a real victim/
  // complaint node (from cross-victim correlation) can be prepended at an
  // earlier layer without the searched wallet losing its "this is the
  // target" visual treatment.
  isTarget?: boolean;
  // The target IS a suspected fraudster wallet only when real evidence says
  // so — at least one victim's complaint actually names it (see
  // investigation.tsx, where this is set from real `linkedComplaints`, never
  // hardcoded). A target with no complaints against it stays a neutral
  // "searched wallet": ARGUS has no evidence to call it anything else.
  isSuspectedFraudster?: boolean;
  x: number;
  y: number;
}

export interface TraceEdge {
  id: string;
  from: string;
  to: string;
  method: string;
  amount: string;
  timestamp: string;
  // Real on-chain hash for this transfer — the actual evidence, not a
  // fabricated confidence score.
  txHash?: string;
  dataSource: string;
  resolved: boolean;
}

// --- Risk Signals ---
export interface RiskSignal {
  id: string;
  label: string;
  contribution: number;
  // Whether this feature pushed the score up or down — real, from the
  // model's own SHAP output, not inferred from the contribution magnitude
  // (which is always positive; direction is a separate axis).
  direction: "increases_risk" | "decreases_risk";
  evidence: string;
  dataSource: string;
  detail: string;
}
