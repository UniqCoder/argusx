// ============================================================
// ARGUS — Mock Intelligence Data
// All mock data is separated from UI components.
// Replace with live API/WebSocket calls when backend is ready.
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
  | "NFT Fraud";

export interface InvestigationCase {
  id: string;
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

export const MOCK_CASES: InvestigationCase[] = [
  {
    id: "UG-2026-04821",
    fraudType: "Investment Scam",
    blockchain: "ETH",
    // Real address, verified traceable against the live backend — not a
    // display-truncated placeholder (those contain a literal "..." and get
    // rejected by the blockchain explorer as a malformed address).
    reportedWallet: "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045",
    traceStatus: "critical",
    networkSignal: "HIGH",
    riskScore: 94,
    victimCount: 4,
    lastActivity: "2 min ago",
    description:
      "High-volume wallet linked to 4 independent NCRP complaints across 3 states.",
  },
  {
    id: "UG-2026-03309",
    fraudType: "Task Fraud",
    blockchain: "TRON",
    reportedWallet: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
    traceStatus: "live-trace",
    networkSignal: "HIGH",
    riskScore: 87,
    victimCount: 7,
    lastActivity: "8 min ago",
    description:
      "USDT-TRC20 trail across 6 intermediate wallets. Approaching known exchange.",
  },
  {
    id: "UG-2026-02187",
    fraudType: "Ransomware",
    blockchain: "BTC",
    reportedWallet: "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
    traceStatus: "vasp-identified",
    networkSignal: "MEDIUM",
    riskScore: 79,
    victimCount: 2,
    lastActivity: "1 hr ago",
    description:
      "Ransomware payment traced to mixer then to Binance deposit address.",
  },
  {
    id: "UG-2026-01654",
    fraudType: "Rug Pull",
    blockchain: "BSC",
    reportedWallet: "0xE3B9...2D4A",
    traceStatus: "evidence-ready",
    networkSignal: "MEDIUM",
    riskScore: 72,
    victimCount: 128,
    lastActivity: "3 hrs ago",
    description:
      "Smart contract drain — funds bridged to ETH then deposited at exchange.",
  },
  {
    id: "UG-2026-00891",
    fraudType: "Phishing",
    blockchain: "ETH",
    reportedWallet: "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    traceStatus: "network-signal",
    networkSignal: "LOW",
    riskScore: 61,
    victimCount: 3,
    lastActivity: "6 hrs ago",
    description:
      "Wallet clusters across 3 phishing victims converge at same intermediate.",
  },
  {
    id: "UG-2026-00312",
    fraudType: "Sextortion",
    blockchain: "BTC",
    reportedWallet: "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    traceStatus: "closed",
    networkSignal: "NONE",
    riskScore: 45,
    victimCount: 1,
    lastActivity: "2 days ago",
    description:
      "Single-victim sextortion. Evidence trail complete. Freeze request submitted.",
  },
];

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

export const MOCK_EVENTS: IntelEvent[] = [
  {
    id: "evt-001",
    severity: "CRITICAL",
    type: "DEPOSIT ALERT",
    message: "Flagged wallet approaching known exchange deposit address.",
    caseId: "UG-2026-04821",
    wallet: "0x7A92...B4C1",
    timestamp: "Just now",
    read: false,
  },
  {
    id: "evt-002",
    severity: "HIGH",
    type: "NETWORK SIGNAL",
    message: "Wallet linked to 4 independent victim complaints.",
    caseId: "UG-2026-04821",
    wallet: "0x7A92...B4C1",
    timestamp: "2 min ago",
    read: false,
  },
  {
    id: "evt-003",
    severity: "INFO",
    type: "TRACE UPDATE",
    message: "Hop 3 resolved. Intermediate wallet identified on TRON network.",
    caseId: "UG-2026-03309",
    wallet: "TXqA8...72Bc",
    timestamp: "8 min ago",
    read: false,
  },
  {
    id: "evt-004",
    severity: "HIGH",
    type: "VASP ATTRIBUTION",
    message: "Possible exchange identified: Binance deposit cluster match.",
    caseId: "UG-2026-02187",
    wallet: "1A1z...mXVf",
    timestamp: "42 min ago",
    read: true,
  },
  {
    id: "evt-005",
    severity: "MEDIUM",
    type: "CROSS-CHAIN EVENT",
    message:
      "Bridge interaction detected. Funds moved ETH → TRON via Poly Bridge.",
    caseId: "UG-2026-01654",
    wallet: "0xE3B9...2D4A",
    timestamp: "1 hr ago",
    read: true,
  },
  {
    id: "evt-006",
    severity: "MEDIUM",
    type: "RAPID-HOP PATTERN",
    message: "12 wallet hops in under 4 minutes. Layering pattern detected.",
    caseId: "UG-2026-03309",
    wallet: "TXqA8...72Bc",
    timestamp: "2 hrs ago",
    read: true,
  },
];

// --- Trace Graph Nodes ---
export type NodeType =
  "victim" | "reported" | "intermediate" | "bridge" | "mixer" | "exchange";

export interface TraceNode {
  id: string;
  type: NodeType;
  label: string;
  address: string;
  blockchain: Blockchain;
  riskScore: number;
  resolved: boolean;
  amount?: string;
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
  confidence: number;
  heuristic: string;
  dataSource: string;
  resolved: boolean;
}

export const MOCK_TRACE_NODES: TraceNode[] = [
  {
    id: "n1",
    type: "victim",
    label: "Victim Wallet",
    address: "0x1F4C...A29E",
    blockchain: "ETH",
    riskScore: 0,
    resolved: true,
    amount: "2.4 ETH",
    x: 120,
    y: 280,
  },
  {
    id: "n2",
    type: "reported",
    label: "Reported Wallet",
    address: "0x7A92...B4C1",
    blockchain: "ETH",
    riskScore: 94,
    resolved: true,
    amount: "2.4 ETH",
    x: 300,
    y: 280,
  },
  {
    id: "n3",
    type: "intermediate",
    label: "Intermediate #1",
    address: "0x3D81...F72A",
    blockchain: "ETH",
    riskScore: 71,
    resolved: true,
    amount: "2.38 ETH",
    x: 480,
    y: 180,
  },
  {
    id: "n4",
    type: "intermediate",
    label: "Intermediate #2",
    address: "0xC52A...881B",
    blockchain: "ETH",
    riskScore: 68,
    resolved: true,
    amount: "2.35 ETH",
    x: 480,
    y: 380,
  },
  {
    id: "n5",
    type: "bridge",
    label: "Cross-Chain Bridge",
    address: "Poly Bridge v2",
    blockchain: "ETH",
    riskScore: 30,
    resolved: true,
    amount: "2.35 ETH",
    x: 660,
    y: 280,
  },
  {
    id: "n6",
    type: "mixer",
    label: "Mixer Service",
    address: "Tornado Cash",
    blockchain: "ETH",
    riskScore: 85,
    resolved: false,
    amount: "—",
    x: 840,
    y: 160,
  },
  {
    id: "n7",
    type: "exchange",
    label: "Exchange / VASP",
    address: "Binance Cluster",
    blockchain: "ETH",
    riskScore: 20,
    resolved: false,
    amount: "—",
    x: 840,
    y: 380,
  },
];

export const MOCK_TRACE_EDGES: TraceEdge[] = [
  {
    id: "e1",
    from: "n1",
    to: "n2",
    method: "Direct Transfer",
    amount: "2.4 ETH",
    timestamp: "2026-08-28 14:22",
    confidence: 99,
    heuristic: "Direct on-chain transfer",
    dataSource: "Etherscan",
    resolved: true,
  },
  {
    id: "e2",
    from: "n2",
    to: "n3",
    method: "Fan-out",
    amount: "1.2 ETH",
    timestamp: "2026-08-28 14:28",
    confidence: 94,
    heuristic: "Fan-out split pattern",
    dataSource: "Etherscan",
    resolved: true,
  },
  {
    id: "e3",
    from: "n2",
    to: "n4",
    method: "Fan-out",
    amount: "1.18 ETH",
    timestamp: "2026-08-28 14:28",
    confidence: 94,
    heuristic: "Fan-out split pattern",
    dataSource: "Etherscan",
    resolved: true,
  },
  {
    id: "e4",
    from: "n3",
    to: "n5",
    method: "Bridge Deposit",
    amount: "2.35 ETH",
    timestamp: "2026-08-28 14:41",
    confidence: 87,
    heuristic: "Bridge event cross-chain match",
    dataSource: "Poly Bridge API",
    resolved: true,
  },
  {
    id: "e5",
    from: "n4",
    to: "n5",
    method: "Bridge Deposit",
    amount: "2.35 ETH",
    timestamp: "2026-08-28 14:41",
    confidence: 87,
    heuristic: "Bridge event cross-chain match",
    dataSource: "Poly Bridge API",
    resolved: true,
  },
  {
    id: "e6",
    from: "n5",
    to: "n6",
    method: "Mixer Deposit",
    amount: "~2.3 ETH",
    timestamp: "—",
    confidence: 61,
    heuristic: "Known mixer contract interaction",
    dataSource: "Forta Network",
    resolved: false,
  },
  {
    id: "e7",
    from: "n5",
    to: "n7",
    method: "Exchange Deposit",
    amount: "~2.3 ETH",
    timestamp: "—",
    confidence: 72,
    heuristic: "Exchange cluster heuristic",
    dataSource: "Arkham Intel",
    resolved: false,
  },
];

// --- Risk Signals ---
export interface RiskSignal {
  id: string;
  label: string;
  contribution: number;
  evidence: string;
  dataSource: string;
  detail: string;
}

export const MOCK_RISK_SIGNALS: RiskSignal[] = [
  {
    id: "rs1",
    label: "Multiple Victim Complaints",
    contribution: 28,
    evidence: "4 independent NCRP complaints linking to this wallet cluster",
    dataSource: "NCRP Database",
    detail: "Complaint IDs: 2026/ETH/0041, 0089, 0123, 0201",
  },
  {
    id: "rs2",
    label: "Rapid-Hop Pattern",
    contribution: 18,
    evidence: "12 wallet-to-wallet transfers within 4 minutes",
    dataSource: "Etherscan",
    detail: "Block range 19,822,310–19,822,318. Layering signature.",
  },
  {
    id: "rs3",
    label: "Cross-Chain Movement",
    contribution: 16,
    evidence: "Funds bridged ETH → TRON via Poly Bridge v2",
    dataSource: "Poly Bridge API",
    detail: "Bridge tx: 0xAB7C...F221. TRON destination: TXqA8...72Bc",
  },
  {
    id: "rs4",
    label: "Bridge Interaction",
    contribution: 14,
    evidence:
      "Interaction with Poly Bridge v2 — high-risk cross-chain infrastructure",
    dataSource: "Forta Network",
    detail: "Bridge risk tier: HIGH. Associated with 14 prior fraud cases.",
  },
  {
    id: "rs5",
    label: "Known High-Risk Cluster",
    contribution: 12,
    evidence:
      "Intermediate wallet appears in Arkham Intel high-risk cluster #HRC-812",
    dataSource: "Arkham Intel",
    detail: "Cluster contains 47 addresses. Last flagged: 2026-08-14.",
  },
  {
    id: "rs6",
    label: "Transaction Velocity",
    contribution: 9,
    evidence: "22 transactions in 6 hours — 8x above baseline for wallet age",
    dataSource: "Etherscan",
    detail: "Wallet age: 11 days. Expected tx/day for age bracket: 0.4.",
  },
];

// --- Evidence Timeline ---
export interface EvidenceEvent {
  id: string;
  title: string;
  timestamp: string;
  method: string;
  dataSource: string;
  confidence: number;
  detail: string;
  type:
    | "complaint"
    | "report"
    | "trace"
    | "hop"
    | "cross-chain"
    | "signal"
    | "vasp"
    | "evidence";
}

export const MOCK_EVIDENCE_TRAIL: EvidenceEvent[] = [
  {
    id: "ev1",
    title: "Complaint Received",
    timestamp: "2026-08-26 09:14",
    method: "NCRP Portal Submission",
    dataSource: "NCRP",
    confidence: 100,
    detail: "Complaint ID 2026/ETH/0041 filed. ₹3.2L reported lost.",
    type: "complaint",
  },
  {
    id: "ev2",
    title: "Wallet Reported",
    timestamp: "2026-08-26 09:22",
    method: "Investigator Manual Entry",
    dataSource: "Case Intake",
    confidence: 100,
    detail: "Wallet 0x7A92...B4C1 submitted for tracing.",
    type: "report",
  },
  {
    id: "ev3",
    title: "Trace Started",
    timestamp: "2026-08-26 09:23",
    method: "Automated On-Chain Crawl",
    dataSource: "Argus Engine",
    confidence: 100,
    detail: "Etherscan + internal graph query initiated.",
    type: "trace",
  },
  {
    id: "ev4",
    title: "Hop 1 Resolved",
    timestamp: "2026-08-26 09:24",
    method: "Direct Transfer Heuristic",
    dataSource: "Etherscan",
    confidence: 99,
    detail: "0x7A92...B4C1 → 0x3D81...F72A. 1.2 ETH. Block 19822311.",
    type: "hop",
  },
  {
    id: "ev5",
    title: "Hop 2 Resolved",
    timestamp: "2026-08-26 09:24",
    method: "Fan-out Pattern Detection",
    dataSource: "Etherscan",
    confidence: 94,
    detail:
      "Simultaneous fan-out to two intermediate wallets. Layering signature.",
    type: "hop",
  },
  {
    id: "ev6",
    title: "Cross-Chain Event Detected",
    timestamp: "2026-08-26 09:31",
    method: "Bridge Event Correlation",
    dataSource: "Poly Bridge API",
    confidence: 87,
    detail: "Poly Bridge deposit. ETH → TRON. Destination: TXqA8...72Bc.",
    type: "cross-chain",
  },
  {
    id: "ev7",
    title: "Network Signal Detected",
    timestamp: "2026-08-26 09:45",
    method: "Cross-Victim Correlation",
    dataSource: "Argus Engine",
    confidence: 92,
    detail:
      "Wallet cluster linked to 4 independent complaints. Network signal: HIGH.",
    type: "signal",
  },
  {
    id: "ev8",
    title: "VASP Identified",
    timestamp: "2026-08-26 10:02",
    method: "Exchange Cluster Heuristic",
    dataSource: "Arkham Intel",
    confidence: 72,
    detail:
      "Destination matches Binance deposit cluster #BC-7741. Freeze advised.",
    type: "vasp",
  },
  {
    id: "ev9",
    title: "Evidence Ready",
    timestamp: "2026-08-26 10:15",
    method: "Automated Report Assembly",
    dataSource: "Argus Engine",
    confidence: 94,
    detail:
      "Court-ready evidence trail complete. 8 events. 6 on-chain proofs. 2 heuristics.",
    type: "evidence",
  },
];

// --- Alert Feed ---
export const MOCK_ALERTS = MOCK_EVENTS;

// --- Command Center Status ---
export const COMMAND_CENTER_STATS = {
  activeCases: 5,
  liveTraces: 2,
  networkSignals: 3,
  criticalAlerts: 1,
};

// --- Network Signal ---
export const MOCK_NETWORK_SIGNAL = {
  wallet: "0x7A92...B4C1",
  victims: 4,
  complaints: 6,
  states: 3,
  daysSinceFirst: 12,
  signalStrength: "HIGH" as const,
  totalFundsAtRisk: "₹14.8L",
};
