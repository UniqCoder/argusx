// ============================================================
// useWalletTrace + useWalletRisk
// Real data only — no silent mock fallback on error or empty results.
// Callers read `error`/`loading` and show their own state; node/edge
// coordinates are placeholders (0,0) here, computed for real by
// useForceLayout (src/hooks/use-force-layout.ts), not by this hook.
//
// useWalletTrace routes through the real v2 provenance engine (anchor +
// taint-propagation trace, /api/v1/anchors + /api/v1/engine/trace) instead
// of the v1 endpoint. v1 only lists an address's own direct transactions
// and had no real per-node classification — the frontend used to fake
// "bridge"/"exchange" node types by array position, not real detection.
// v2 does genuine branching multi-hop BFS with real terminal classification
// (VASP / mixer / bridge, from live registries) and a real parent-address
// edge, so a wallet's actual mixers/bridges/VASPs render as what they are.
// ============================================================
import { useState, useEffect } from "react";
import { createAnchor, runEngineTrace, getWalletRisk } from "@/lib/api";
import { useSessionStore } from "@/store/session-store";
import type { Chain, TaintNodeRead, RiskResponse } from "@/lib/api-types";
import type { TraceNode, TraceEdge, RiskSignal } from "@/lib/mock-data";

const TERMINAL_TYPE: Record<string, TraceNode["type"]> = {
  VASP: "exchange",
  MIXER_BOUNDARY: "mixer",
  BRIDGE: "bridge",
};

function nodeTypeFor(node: TaintNodeRead): TraceNode["type"] {
  if (node.hop === 0) return "reported";
  if (node.terminal_kind) return TERMINAL_TYPE[node.terminal_kind] ?? "intermediate";
  return "intermediate";
}

function nodeLabelFor(node: TaintNodeRead): string {
  if (node.hop === 0) return "Searched wallet";
  if (node.entity_name) return node.entity_name;
  if (node.terminal_kind === "MIXER_BOUNDARY") return "Mixer";
  if (node.terminal_kind === "BRIDGE") return "Bridge";
  if (node.terminal_kind === "DUST") return "Dust (below floor)";
  if (node.terminal_kind === "DEPTH_LIMIT") return "Depth limit reached";
  if (node.terminal_kind === "NODE_LIMIT") return "Trace budget reached";
  return `Hop ${node.hop}`;
}

// Real taint-engine nodes/terminals -> the graph shape the UI renders.
// parent_address/tx_hash/tx_amount (added specifically for this) let real
// branching (multiple children per node) and real edge evidence render,
// instead of a flat hop list.
function traceResultToGraph(
  nodes: TaintNodeRead[],
): { nodes: TraceNode[]; edges: TraceEdge[] } {
  const idByAddress = new Map<string, string>();
  nodes.forEach((n, i) => idByAddress.set(n.address, `n${i}`));

  const graphNodes: TraceNode[] = nodes.map((n) => {
    const id = idByAddress.get(n.address)!;
    const node: TraceNode = {
      id,
      type: nodeTypeFor(n),
      label: nodeLabelFor(n),
      address:
        n.address.length > 18
          ? n.address.slice(0, 8) + "..." + n.address.slice(-4)
          : n.address,
      blockchain: n.chain as TraceNode["blockchain"],
      x: 0,
      y: 0,
      resolved: true,
    };
    if (n.tx_amount != null) node.amount = `${n.tx_amount} ${n.chain}`;
    return node;
  });

  const graphEdges: TraceEdge[] = nodes
    .filter((n) => n.parent_address && n.tx_hash)
    .map((n) => {
      const fromId = idByAddress.get(n.parent_address!);
      const toId = idByAddress.get(n.address);
      return {
        id: `${fromId}-${toId}`,
        from: fromId ?? "n0",
        to: toId ?? "n0",
        method: "Direct Transfer",
        amount: n.tx_amount != null ? `${n.tx_amount} ${n.chain}` : "—",
        timestamp: "",
        txHash: n.tx_hash!,
        dataSource:
          n.chain === "BTC"
            ? "Blockstream"
            : n.chain === "TRON"
              ? "TronGrid"
              : "Blockscout",
        resolved: true,
      };
    });

  return { nodes: graphNodes, edges: graphEdges };
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

    const investigator = useSessionStore.getState().email ?? "dashboard-investigator";

    (async () => {
      // Every trace registers its own Class-C ("investigator hypothesis")
      // anchor — real provenance for why this address was traced, never
      // strong enough on its own to justify a freeze/block decision. A
      // unique source_ref per trace avoids colliding with the anchor
      // uniqueness constraint on repeat searches of the same address.
      const anchor = await createAnchor({
        address,
        chain,
        attestation_class: "C",
        attestation_type: "INVESTIGATOR_ASSERTED",
        source_ref: `dashboard-trace-${Date.now()}`,
        asserted_by: investigator,
      });

      const result = await runEngineTrace({
        anchor_id: anchor.id,
        max_hops: 8,
        max_nodes: 80,
      });

      if (cancelled) return;
      const graph = traceResultToGraph(result.nodes);
      setNodes(graph.nodes);
      setEdges(graph.edges);

      const vaspTerminals = result.terminals.filter(
        (n) => n.terminal_kind === "VASP",
      );
      const best = vaspTerminals.sort(
        (a, b) => (b.tx_amount ?? 0) - (a.tx_amount ?? 0),
      )[0];
      setVasp(best?.entity_name ?? null);
    })()
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
