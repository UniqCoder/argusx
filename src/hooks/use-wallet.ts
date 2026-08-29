// ============================================================
// useWalletTrace + useWalletRisk
// Falls back to MOCK_TRACE_* / MOCK_RISK_SIGNALS on error.
// ============================================================
import { useState, useEffect } from "react";
import { getWalletTrace, getWalletRisk } from "@/lib/api";
import type { Chain, TraceResponse, RiskResponse } from "@/lib/api-types";
import {
  MOCK_TRACE_NODES,
  MOCK_TRACE_EDGES,
  MOCK_RISK_SIGNALS,
  type TraceNode,
  type TraceEdge,
  type RiskSignal,
} from "@/lib/mock-data";

// Map raw hops from the API into the graph node/edge format the UI expects
function hopsToGraph(
  hops: TraceResponse["path"],
  address: string,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  if (hops.length === 0)
    return { nodes: MOCK_TRACE_NODES, edges: MOCK_TRACE_EDGES };

  // Build unique address list
  const addrList: string[] = [address];
  for (const hop of hops) {
    if (!addrList.includes(hop.from_address)) addrList.push(hop.from_address);
    if (!addrList.includes(hop.to_address)) addrList.push(hop.to_address);
  }

  const TYPES: TraceNode["type"][] = [
    "victim",
    "reported",
    "intermediate",
    "intermediate",
    "bridge",
    "exchange",
  ];
  const W = 160;

  const nodes: TraceNode[] = addrList.map((addr, i) => {
    const prevHop = hops[i - 1];
    const node: TraceNode = {
      id: `n${i}`,
      type: (TYPES[Math.min(i, TYPES.length - 1)] ??
        "intermediate") as TraceNode["type"],
      label:
        i === 0
          ? "Victim"
          : i === addrList.length - 1
            ? "Exchange"
            : `Hop ${i}`,
      address:
        addr.length > 18 ? addr.slice(0, 8) + "..." + addr.slice(-4) : addr,
      blockchain: (hops[0]?.chain ?? "ETH") as TraceNode["blockchain"],
      riskScore: i === addrList.length - 1 ? 88 : i === 1 ? 72 : 30,
      x: 80 + i * W,
      y: i % 2 === 0 ? 200 : 130,
      resolved: true,
    };
    if (prevHop != null) node.amount = `${prevHop.amount} ${prevHop.chain}`;
    return node;
  });

  const edges: TraceEdge[] = hops.map((hop, i) => {
    const fromIdx = addrList.indexOf(hop.from_address);
    const toIdx = addrList.indexOf(hop.to_address);
    return {
      id: `e${i}`,
      from: `n${fromIdx >= 0 ? fromIdx : i}`,
      to: `n${toIdx >= 0 ? toIdx : i + 1}`,
      method: "Direct Transfer",
      amount: `${hop.amount} ${hop.chain}`,
      timestamp: hop.timestamp,
      confidence: 92,
      heuristic: "On-chain trace (live)",
      dataSource:
        hop.chain === "BTC"
          ? "Blockstream"
          : hop.chain === "TRON"
            ? "TronGrid"
            : "Etherscan",
      resolved: true,
    };
  });

  return { nodes, edges };
}

// ── Trace hook ─────────────────────────────────────────────────────────────
export function useWalletTrace(address: string | null, chain: Chain) {
  const [nodes, setNodes] = useState<TraceNode[]>(MOCK_TRACE_NODES);
  const [edges, setEdges] = useState<TraceEdge[]>(MOCK_TRACE_EDGES);
  const [vasp, setVasp] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!address) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    getWalletTrace(address, chain)
      .then((data) => {
        if (cancelled) return;
        if (data.path.length > 0) {
          const graph = hopsToGraph(data.path, address);
          setNodes(graph.nodes);
          setEdges(graph.edges);
        }
        setVasp(data.nearest_vasp ?? null);
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Trace failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [address, chain]);

  return { nodes, edges, vasp, loading, error };
}

// ── Risk hook ──────────────────────────────────────────────────────────────
export function useWalletRisk(address: string | null, chain: Chain) {
  const [riskScore, setRiskScore] = useState<number>(94);
  const [riskTier, setRiskTier] = useState<string>("critical");
  const [signals, setSignals] = useState<RiskSignal[]>(MOCK_RISK_SIGNALS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!address) return;
    let cancelled = false;
    setLoading(true);
    setError(null);

    getWalletRisk(address, chain)
      .then((data: RiskResponse) => {
        if (cancelled) return;
        setRiskScore(Math.round(data.risk_score * 100));
        setRiskTier(data.risk_tier);
        if (data.evidence.length > 0) {
          setSignals(
            data.evidence.map((ev, i) => ({
              id: `ev${i}`,
              label: ev.feature_name
                .replace(/_/g, " ")
                .replace(/\b\w/g, (c) => c.toUpperCase()),
              contribution: Math.max(
                1,
                Math.round(Math.abs(ev.contribution) * 30),
              ),
              evidence: `SHAP: ${ev.contribution.toFixed(3)} (${ev.direction.replace(/_/g, " ")})`,
              dataSource: "XGBoost / Elliptic++ Dataset",
              detail: `Feature "${ev.feature_name}" ${ev.direction.replace(/_/g, " ")} the risk score.`,
            })),
          );
        }
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Risk scoring failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [address, chain]);

  return { riskScore, riskTier, signals, loading, error };
}
