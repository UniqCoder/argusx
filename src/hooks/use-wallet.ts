// ============================================================
// useWalletTrace + useWalletRisk
// Real data only — no silent mock fallback on error or empty results.
// Callers read `error`/`loading` and show their own state; node/edge
// coordinates are placeholders (0,0) here, computed for real by
// useForceLayout (src/hooks/use-force-layout.ts), not by this hook.
// ============================================================
import { useState, useEffect } from "react";
import { getWalletTrace, getWalletRisk } from "@/lib/api";
import type { Chain, TraceResponse, RiskResponse } from "@/lib/api-types";
import type { TraceNode, TraceEdge, RiskSignal } from "@/lib/mock-data";

// Map raw hops from the API into the graph node/edge identity format the UI
// expects. Positions (x/y) are 0 here — useForceLayout owns those.
function hopsToGraph(
  hops: TraceResponse["path"],
  address: string,
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  if (hops.length === 0) {
    // Real, empty result: the wallet was queried and no onward hops were
    // found. Show it as a single unconnected node, not 7 mock nodes.
    return {
      nodes: [
        {
          id: "n0",
          type: "reported",
          label: "Searched wallet",
          address:
            address.length > 18
              ? address.slice(0, 8) + "..." + address.slice(-4)
              : address,
          blockchain: "ETH",
          resolved: true,
          x: 0,
          y: 0,
        },
      ],
      edges: [],
    };
  }

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

  // Node label reflects position in the chain, not a fabricated role —
  // "Victim"/"Exchange" implied intelligence (mixer detection, VASP
  // attribution) the backend doesn't actually compute per-hop.
  const nodes: TraceNode[] = addrList.map((addr, i) => {
    const prevHop = hops[i - 1];
    const node: TraceNode = {
      id: `n${i}`,
      type: (TYPES[Math.min(i, TYPES.length - 1)] ??
        "intermediate") as TraceNode["type"],
      label: i === 0 ? "Searched wallet" : `Hop ${i}`,
      address:
        addr.length > 18 ? addr.slice(0, 8) + "..." + addr.slice(-4) : addr,
      blockchain: (hops[0]?.chain ?? "ETH") as TraceNode["blockchain"],
      x: 0,
      y: 0,
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
      txHash: hop.tx_hash,
      dataSource:
        hop.chain === "BTC"
          ? "Blockstream"
          : hop.chain === "TRON"
            ? "TronGrid"
            : "Blockscout",
      resolved: true,
    };
  });

  return { nodes, edges };
}

// ── Trace hook ─────────────────────────────────────────────────────────────
export function useWalletTrace(address: string | null, chain: Chain) {
  const [nodes, setNodes] = useState<TraceNode[]>([]);
  const [edges, setEdges] = useState<TraceEdge[]>([]);
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
        const graph = hopsToGraph(data.path, address);
        setNodes(graph.nodes);
        setEdges(graph.edges);
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
  const [riskScore, setRiskScore] = useState<number | null>(null);
  const [riskTier, setRiskTier] = useState<string | null>(null);
  const [signals, setSignals] = useState<RiskSignal[]>([]);
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
