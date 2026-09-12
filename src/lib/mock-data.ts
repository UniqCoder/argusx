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
export type Blockchain = "BTC" | "ETH" | "TRON" | "BSC" | "Polygon";
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
  fraudType: FraudType;
  blockchain: Blockchain;
  reportedWallet: string;
  traceStatus: CaseStatus;
  networkSignal: "HIGH" | "MEDIUM" | "LOW" | "NONE";
  riskScore: number;
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
  // BRIDGE/DUST/DEPTH_LIMIT/NODE_LIMIT/NO_OUTFLOW), when this node is one.
  terminalKind?: string;
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
  evidence: string;
  dataSource: string;
  detail: string;
}
