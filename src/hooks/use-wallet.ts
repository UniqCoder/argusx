// ============================================================
// useWalletTrace + useWalletRisk
// Real data only — no silent mock fallback on error or empty results.
// Callers read `error`/`loading` and show their own state; node/edge
// coordinates are placeholders (0,0) here, computed for real by
// useTraceLayout (src/hooks/use-trace-layout.ts), not by this hook.
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
import { useState, useEffect, useRef } from "react";
import { createAnchor, getWalletRisk } from "@/lib/api";
import { streamTrace } from "@/lib/trace-stream";
import type { TraceProgress, TraceStreamHandlers } from "@/lib/trace-stream";
import { useSessionStore } from "@/store/session-store";
import { useCaseContext } from "@/store/case-context-store";
import type {
  Chain,
  TaintNodeRead,
  RiskResponse,
  EngineTraceResult,
} from "@/lib/api-types";
import type { TraceNode, TraceEdge, RiskSignal } from "@/lib/mock-data";
// tx_amount / seed_value / taint_fraction et al arrive as Decimal STRINGS
// (Pydantic serialises Decimal that way). See src/lib/decimal.ts.
import { toNum, formatAmount } from "@/lib/decimal";

const TERMINAL_TYPE: Record<string, TraceNode["type"]> = {
  VASP: "exchange",
  MIXER_BOUNDARY: "mixer",
  BRIDGE: "bridge",
};

function nodeTypeFor(node: TaintNodeRead): TraceNode["type"] {
  if (node.hop === 0) return "reported";
  if (node.terminal_kind)
    return TERMINAL_TYPE[node.terminal_kind] ?? "intermediate";
  return "intermediate";
}

function nodeLabelFor(node: TaintNodeRead): string {
  // A real attributed entity is always more informative than a positional
  // label. This used to check hop 0 first, so a hop-0 node that IS a known
  // exchange read as "Searched wallet" instead of "Binance", and every hop-0
  // node in a multi-origin case (several victims converging on one wallet)
  // read as "Searched wallet" regardless of which one it was.
  if (node.entity_name) return node.entity_name;
  if (node.hop === 0) return "Searched wallet";
  if (node.terminal_kind === "MIXER_BOUNDARY") return "Mixer";
  if (node.terminal_kind === "BRIDGE") return "Bridge";
  if (node.terminal_kind === "DUST") return "Diluted below floor";
  if (node.terminal_kind === "DILUTED_OUTFLOW") return "All branches dust";
  if (node.terminal_kind === "DEPTH_LIMIT") return "Depth limit reached";
  if (node.terminal_kind === "NODE_LIMIT") return "Trace budget reached";
  if (node.terminal_kind === "NO_OUTFLOW") return "Funds still here";
  if (node.terminal_kind === "EXPLORER_UNAVAILABLE")
    return "Explorer unavailable";
  return `Hop ${node.hop}`;
}

// Human-readable explanation of why a node is a dead end. Every terminal must
// be able to answer "why does the trail stop here?" — an unexplained stop is
// indistinguishable from a bug, which is exactly how the sparse graphs read.
export function terminalExplanation(
  node: TraceNode,
  asset: string,
): string | null {
  switch (node.terminalKind) {
    case "VASP":
      return `Funds reached ${node.entity ?? "a known exchange/VASP"} — an attributable off-ramp. This is the operationally important endpoint: a freeze request goes here.`;
    case "MIXER_BOUNDARY":
      return "Funds entered a known mixer. The trace stops here by design — ARGUS does not claim to see through mixers.";
    case "BRIDGE":
      return "Funds reached a known cross-chain bridge contract. Value left this chain here; continuing the trail requires correlating the destination chain.";
    case "NO_OUTFLOW":
      return `Tainted funds arrived here and have not moved on within the transactions checked. This is the most actionable terminal — the money is still sitting at this address.`;
    case "DUST":
      return `After haircut apportionment this address's tainted share fell below the dilution floor, so following it further would not be supportable evidence.`;
    case "DILUTED_OUTFLOW":
      return `This address does send funds onward, but every onward transfer carried less than the dust floor of tainted ${asset} after apportionment${
        node.prunedChildCount
          ? ` (${node.prunedChildCount} branch${node.prunedChildCount === 1 ? "" : "es"} set aside)`
          : ""
      }.`;
    case "DEPTH_LIMIT":
      return "The trace hit its maximum hop depth here. Money may well have moved further — raise the depth to keep going.";
    case "NODE_LIMIT":
      return "The trace budget ran out with money still moving through this address. This branch is unresolved, not clean.";
    case "EXPLORER_UNAVAILABLE":
      return "The blockchain explorer could not be reached for this address, so this branch is incomplete. Retrying may resolve it.";
    default:
      return null;
  }
}

// Real taint-engine nodes/terminals -> the graph shape the UI renders.
// parent_address/tx_hash/tx_amount (added specifically for this) let real
// branching (multiple children per node) and real edge evidence render,
// instead of a flat hop list.
// Node identity is (address, chain), NOT array position and NOT address alone.
// Array position produced a new id for the same wallet on every re-fetch;
// address alone would silently merge the same address on two different chains
// into one node the moment cross-chain tracing lands.
function nodeKey(address: string, chain: string): string {
  return `${chain}:${address.toLowerCase()}`;
}

function traceResultToGraph(
  nodes: TaintNodeRead[],
  asset: string,
): { nodes: TraceNode[]; edges: TraceEdge[]; orphanedEdges: number } {
  const idByKey = new Map<string, string>();
  // Secondary index: address -> every id that address has on ANY chain. Needed
  // because an edge can legitimately CROSS chains (a bridge hand-off: the
  // parent sits on Ethereum, the child on Polygon), and a strict
  // (address, chain) lookup misses the parent in exactly that case. This was a
  // real defect caught by the trace-diagnostics panel — the cross-chain hops
  // were being counted as orphaned and silently dropped from the graph.
  const idsByAddress = new Map<string, string[]>();
  nodes.forEach((n) => {
    const k = nodeKey(n.address, n.chain);
    // First occurrence wins, so the id stays stable even if the backend ever
    // returns the same address twice (it keys visited by (address, chain), so
    // it shouldn't — but the UI must not produce duplicate React keys if it
    // ever does).
    if (!idByKey.has(k)) {
      const id = `n${idByKey.size}`;
      idByKey.set(k, id);
      const addr = n.address.toLowerCase();
      idsByAddress.set(addr, [...(idsByAddress.get(addr) ?? []), id]);
    }
  });

  // Resolve an edge endpoint: same chain first (the normal case), then an
  // unambiguous match on another chain (the bridge hand-off). If an address
  // exists on several chains and none is the expected one, the relationship is
  // genuinely ambiguous — return undefined and let the caller count it as
  // dropped rather than guessing which node the money went to.
  const resolveEndpoint = (
    address: string,
    chain: string,
  ): string | undefined => {
    const exact = idByKey.get(nodeKey(address, chain));
    if (exact) return exact;
    const candidates = idsByAddress.get(address.toLowerCase()) ?? [];
    return candidates.length === 1 ? candidates[0] : undefined;
  };

  const graphNodes: TraceNode[] = [];
  const seen = new Set<string>();
  for (const n of nodes) {
    const k = nodeKey(n.address, n.chain);
    if (seen.has(k)) continue;
    seen.add(k);
    const node: TraceNode = {
      id: idByKey.get(k)!,
      type: nodeTypeFor(n),
      label: nodeLabelFor(n),
      address:
        n.address.length > 18
          ? n.address.slice(0, 8) + "..." + n.address.slice(-4)
          : n.address,
      blockchain: n.chain as TraceNode["blockchain"],
      hop: n.hop,
      isTarget: n.hop === 0,
      x: 0,
      y: 0,
      resolved: true,
    };
    // Label the amount in the asset actually traced. This used to interpolate
    // the CHAIN, so a 691.53 USDT transfer rendered as "691.53 TRON".
    if (n.tx_amount != null) node.amount = formatAmount(n.tx_amount, asset);
    if (n.first_tainted_at) node.firstTaintedAt = n.first_tainted_at;
    if (n.terminal_kind) node.terminalKind = n.terminal_kind;
    if (n.entity_name) node.entity = n.entity_name;
    if (n.pruned_child_count) node.prunedChildCount = n.pruned_child_count;
    if (n.pruned_child_value)
      node.prunedChildValue = toNum(n.pruned_child_value);
    if (n.other_asset_child_count)
      node.otherAssetChildCount = n.other_asset_child_count;
    graphNodes.push(node);
  }

  // An edge is only real if BOTH of its endpoints are nodes in this result.
  // This used to fall back to `from: "n0"` when the parent was missing, which
  // fabricated a direct edge from the searched wallet to a node it had no
  // proven relationship with. Drop those and report the count instead.
  let orphanedEdges = 0;
  const graphEdges: TraceEdge[] = [];
  for (const n of nodes) {
    if (!n.parent_address || !n.tx_hash) continue;
    const fromId = resolveEndpoint(n.parent_address, n.chain);
    const toId = resolveEndpoint(n.address, n.chain);
    if (!fromId || !toId) {
      orphanedEdges += 1;
      continue;
    }
    graphEdges.push({
      // Include the tx hash: two different transactions between the same pair
      // of wallets are two different pieces of evidence, and a pair-only id
      // collapsed them into one.
      id: `${fromId}-${toId}-${n.tx_hash.slice(0, 10)}`,
      from: fromId,
      to: toId,
      method: "Direct Transfer",
      amount: n.tx_amount != null ? formatAmount(n.tx_amount, asset) : "—",
      timestamp: n.first_tainted_at ?? "",
      txHash: n.tx_hash,
      dataSource:
        n.chain === "BTC"
          ? "Blockstream"
          : n.chain === "TRON"
            ? "TronGrid"
            : "Blockscout",
      resolved: true,
    });
  }

  return { nodes: graphNodes, edges: graphEdges, orphanedEdges };
}

// Everything the UI needs to describe a trace truthfully, derived from one
// engine result. The terminal, the graph, the inspector, the diagnostics panel
// and the report all read from this — not from separate parallel state.
export interface TraceMeta {
  asset: string;
  assetBasis: string;
  seedValue: number;
  seedBasis: string;
  depthRequested: number;
  depthReached: number;
  terminationReason: string;
  prunedBranchCount: number;
  prunedBranchValue: number;
  otherAssetBranchCount: number;
  nodeCount: number;
  traceId: string;
  reproducibleHash: string;
  orphanedEdges: number;
  completedAt: string;
  /**
   * Where the transaction data came from, as asserted by the ENGINE — not
   * inferred here. Previously this was a client-side check against a hardcoded
   * address prefix, which is the kind of check that silently stops matching.
   *
   *   "live"            every address answered by a public blockchain explorer
   *   "seeded_scenario" every address answered by the seeded-scenario fixture
   *   "mixed"           both
   *
   * Every surface that renders a trace must show a visible badge when this is
   * not "live" — a seeded case must never be able to look like a live one.
   */
  dataSource: "live" | "seeded_scenario" | "mixed";
  /** Which seeded case this is, when dataSource is not "live". */
  scenarioKey: string | null;
}

// Module-level (not component-level) registry of traces in flight, so a rapid
// double-invoke of the effect below for the exact same [address, chain] — which
// React StrictMode does on every mount, and which was confirmed creating two
// real anchors ~5ms apart — starts ONE trace, not two.
//
// It holds an event log rather than just a promise, because the trace now
// streams: a second subscriber that arrives mid-trace replays every node
// already settled and then continues live, so it builds the identical graph.
// A bare shared promise would have given the second subscriber nothing until
// the trace finished, which is exactly the blank wait streaming exists to end.
interface TraceRun {
  events: Array<
    | { kind: "node"; node: TaintNodeRead }
    | { kind: "progress"; progress: TraceProgress }
  >;
  listeners: Set<TraceStreamHandlers>;
  promise: Promise<{ result: EngineTraceResult; vasp: string | null }>;
  controller: AbortController;
}

const _runs = new Map<string, TraceRun>();

async function runStreamingTrace(
  address: string,
  chain: Chain,
  handlers: TraceStreamHandlers,
): Promise<{ result: EngineTraceResult; vasp: string | null }> {
  const key = `${chain}:${address}`;

  const existing = _runs.get(key);
  if (existing) {
    // Replay what has already been settled, then follow along live.
    for (const e of existing.events) {
      if (e.kind === "node") handlers.onNode?.(e.node);
      else handlers.onProgress?.(e.progress);
    }
    existing.listeners.add(handlers);
    return existing.promise;
  }

  // Every trace visits addresses one at a time against public explorers, so the
  // node budget IS the wall-clock budget, and the frontier is value-ordered:
  // the budget is spent on the biggest money first, not on breadth. Raising it
  // does not find "more" money, it finds progressively smaller change.
  //
  // This is a real, disclosed bound, not a shortcut: the backend records the
  // exact max_nodes/max_hops on every Trace row, the result reports
  // depth_reached vs requested, and any branch left unresolved by the budget
  // comes back marked NODE_LIMIT rather than silently dropped.
  const maxNodes = chain === "TRON" ? 30 : 35;

  const investigator =
    useSessionStore.getState().email ?? "dashboard-investigator";
  // Link the anchor to the active case, when there is one, so its real
  // anchor/trace/decision events show up on that case's Evidence Trail.
  // Tracing ad hoc with no case selected still works — case_id stays null.
  const activeCaseId = useCaseContext.getState().activeCaseId;

  const controller = new AbortController();
  const run: TraceRun = {
    events: [],
    listeners: new Set([handlers]),
    controller,
    promise: undefined as never,
  };

  const fanOut: TraceStreamHandlers = {
    onNode: (node) => {
      run.events.push({ kind: "node", node });
      run.listeners.forEach((l) => l.onNode?.(node));
    },
    onProgress: (progress) => {
      run.events.push({ kind: "progress", progress });
      run.listeners.forEach((l) => l.onProgress?.(progress));
    },
  };

  run.promise = (async () => {
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
      ...(activeCaseId ? { case_id: activeCaseId } : {}),
    });

    const result = await streamTrace(
      { anchor_id: anchor.id, max_hops: 8, max_nodes: maxNodes },
      fanOut,
      controller.signal,
    );

    const vaspTerminals = result.terminals.filter(
      (n) => n.terminal_kind === "VASP",
    );
    // tx_amount is a Decimal STRING on the wire, so this must coerce before
    // comparing — subtracting strings happened to work by JS coercion, but
    // `?? 0` on a string and any non-numeric value would not.
    const best = [...vaspTerminals].sort(
      (a, b) => toNum(b.tx_amount) - toNum(a.tx_amount),
    )[0];

    return { result, vasp: best?.entity_name ?? null };
  })();

  _runs.set(key, run);
  run.promise
    .catch(() => {
      /* the caller handles it; this only guards the cleanup below */
    })
    .finally(() => {
      // Cleared shortly after settling so a deliberate re-trace of the same
      // wallet later still fires for real.
      setTimeout(() => {
        if (_runs.get(key) === run) _runs.delete(key);
      }, 2000);
    });
  return run.promise;
}

// A component that started or joined a trace must call this on unmount /
// wallet switch. Without it, navigating away or re-tracing mid-stream left
// the abandoned fetch + SSE parse loop running to completion in the
// background with nothing left to abort it — invisible per-trace, but on a
// long session with several traces started and abandoned it accumulates
// into exactly the kind of steady CPU/network drag that reads as "the UI
// gets slower after a while". Only the LAST listener leaving actually
// aborts the underlying stream, so a second subscriber watching the same
// wallet never has its trace killed out from under it.
//
// The abort is deliberately debounced, not immediate: a route
// mount/remount (TanStack Router re-rendering the investigation workspace
// as `activeWallet` settles) can drop listeners to 0 and re-subscribe the
// SAME [address, chain] a tick later. An immediate abort here killed that
// second, real subscription too — "Backend unreachable... signal is
// aborted without reason" on a trace nobody actually abandoned. Waiting one
// short window lets a same-tick resubscribe cancel the pending abort, while
// a genuinely abandoned stream (user navigated to a different wallet/page
// and never came back) still gets cleaned up shortly after.
const RELEASE_GRACE_MS = 400;

function releaseTraceSubscription(
  address: string,
  chain: Chain,
  handlers: TraceStreamHandlers,
) {
  const key = `${chain}:${address}`;
  const run = _runs.get(key);
  if (!run) return;
  run.listeners.delete(handlers);
  if (run.listeners.size === 0) {
    setTimeout(() => {
      // Still this run, still nobody subscribed, still not aborted —
      // genuinely abandoned. Re-check `_runs.get(key) === run` too: a
      // finished run is replaced/removed on its own schedule, and this
      // stale timer must not touch whatever (if anything) took its place.
      if (_runs.get(key) === run && run.listeners.size === 0) {
        run.controller.abort();
      }
    }, RELEASE_GRACE_MS);
  }
}

// ── Trace hook ─────────────────────────────────────────────────────────────
// `retryKey` lets a caller re-run the same [address, chain] trace (Retry
// button after an EXPLORER_UNAVAILABLE result). The module-level in-flight
// cache still dedupes rapid double-fires; it self-clears ~2s after settling,
// so a deliberate retry fires a genuinely new trace.
export function useWalletTrace(
  address: string | null,
  chain: Chain,
  retryKey = 0,
) {
  const [nodes, setNodes] = useState<TraceNode[]>([]);
  const [edges, setEdges] = useState<TraceEdge[]>([]);
  const [meta, setMeta] = useState<TraceMeta | null>(null);
  const [vasp, setVasp] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  /** Live counters while a trace is running; null once it finishes. */
  const [progress, setProgress] = useState<TraceProgress | null>(null);
  // The traced asset is only known once the engine has settled the anchor,
  // so streamed amounts before that point are labelled with the chain.
  const streamedAsset = useRef("");

  useEffect(() => {
    if (!address) return;
    let cancelled = false;
    // Accumulates streamed nodes for this effect run only. A ref would
    // outlive a wallet switch; this is scoped to the run that created it.
    const streamedNodes: TaintNodeRead[] = [];

    // Clear the PREVIOUS wallet's result before starting the new one. Without
    // this, switching wallets left the old graph on screen — for the full
    // duration of the new trace, which can be a minute against live explorers
    // — while the side panel already showed the NEW address. That is a stale
    // graph presented as the current investigation, and it is exactly the
    // "no stale state between traces" requirement.
    setNodes([]);
    setEdges([]);
    setMeta(null);
    setVasp(null);
    setLoading(true);
    setError(null);
    setProgress(null);
    streamedAsset.current = "";

    // Nodes can arrive in fast bursts (a local/cached backend, or the stream
    // catching up after a slow patch) — without this, every single node
    // triggered its own full `traceResultToGraph` rebuild AND a full
    // `useTraceLayout` recompute (BFS + 30 relaxation passes) AND a full
    // SVG re-render downstream, so a 35-node trace paid that entire cost 35
    // times over instead of once. Coalescing into at most one flush per
    // animation frame caps that to the screen's actual refresh rate — still
    // visibly "growing live", just not re-doing the whole layout on every
    // single network event.
    let flushScheduled = false;
    let flushRaf: number | null = null;
    const flush = () => {
      flushScheduled = false;
      flushRaf = null;
      if (cancelled) return;
      const graph = traceResultToGraph(
        streamedNodes,
        streamedAsset.current || chain,
      );
      setNodes(graph.nodes);
      setEdges(graph.edges);
    };

    // A stable reference — needed so the cleanup below can remove exactly
    // this subscription from the shared run's listener set (see
    // releaseTraceSubscription).
    const handlers: TraceStreamHandlers = {
      // Nodes arrive as the engine settles them, in its own value-ordered
      // sequence. The graph is rebuilt from the accumulated list each time
      // rather than patched incrementally, so streamed and finished traces go
      // through exactly the same `traceResultToGraph` — one representation, no
      // second code path to drift.
      onNode: (node) => {
        if (cancelled) return;
        streamedNodes.push(node);
        if (!flushScheduled) {
          flushScheduled = true;
          flushRaf = requestAnimationFrame(flush);
        }
      },
      onProgress: (p) => {
        if (cancelled) return;
        streamedAsset.current = p.asset || streamedAsset.current;
        setProgress(p);
      },
    };

    runStreamingTrace(address, chain, handlers)
      .then(({ result, vasp: bestVasp }) => {
        if (cancelled) return;
        const asset = result.asset || chain;
        // Rebuild from the authoritative finished result. The streamed nodes
        // and this list agree, but the result is what was persisted and what
        // the report will read, so it is what the screen ends up showing.
        const graph = traceResultToGraph(result.nodes, asset);
        setNodes(graph.nodes);
        setEdges(graph.edges);
        setVasp(bestVasp);
        setMeta({
          asset,
          assetBasis: result.asset_basis ?? "unrecorded",
          seedValue: toNum(result.seed_value),
          seedBasis: result.seed_basis ?? "unrecorded",
          depthRequested: result.max_hops,
          depthReached: result.depth_reached ?? 0,
          terminationReason: result.termination_reason ?? "unrecorded",
          prunedBranchCount: result.pruned_branch_count ?? 0,
          prunedBranchValue: toNum(result.pruned_branch_value),
          otherAssetBranchCount: result.other_asset_branch_count ?? 0,
          nodeCount: result.node_count ?? graph.nodes.length,
          traceId: result.trace_id,
          reproducibleHash: result.reproducible_hash,
          orphanedEdges: graph.orphanedEdges,
          completedAt: result.completed_at,
          dataSource: result.data_source,
          scenarioKey: result.scenario_key,
        });
      })
      .catch((e) => {
        if (!cancelled)
          setError(e instanceof Error ? e.message : "Trace failed");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setProgress(null);
        }
      });

    return () => {
      cancelled = true;
      if (flushRaf != null) cancelAnimationFrame(flushRaf);
      releaseTraceSubscription(address, chain, handlers);
    };
  }, [address, chain, retryKey]);

  return { nodes, edges, meta, vasp, loading, error, progress };
}

// Plain-language summary of why a trace stopped where it did. The UI must never
// present "the trace returned" as "the trace found everything".
export function terminationSummary(meta: TraceMeta): {
  headline: string;
  detail: string;
  complete: boolean;
} {
  const reachedAll = meta.depthReached >= meta.depthRequested;
  switch (meta.terminationReason) {
    case "node_budget":
      return {
        headline: "Trace budget reached — branches left unresolved",
        detail: `The ${meta.nodeCount}-address budget ran out while money was still moving. Reached hop ${meta.depthReached} of ${meta.depthRequested} requested. Unresolved branches are marked on the graph — they are not cleared.`,
        complete: false,
      };
    case "all_branches_dust":
      return {
        headline: `Trail ends at hop ${meta.depthReached}`,
        detail: `Every remaining onward transfer carried less than the dust floor of tainted ${meta.asset} after haircut apportionment${
          meta.prunedBranchCount
            ? `, so ${meta.prunedBranchCount} branch${meta.prunedBranchCount === 1 ? "" : "es"} holding ${formatAmount(meta.prunedBranchValue, meta.asset)} were set aside`
            : ""
        }. Requested ${meta.depthRequested} hops, resolved ${meta.depthReached}.`,
        complete: false,
      };
    case "frontier_exhausted":
      return {
        headline: reachedAll
          ? `Trace complete — ${meta.depthReached} hops resolved`
          : `Trace complete at hop ${meta.depthReached}`,
        detail: `Every reachable branch ended at a real terminal (exchange, mixer, bridge, or funds still sitting). Requested up to ${meta.depthRequested} hops; the money genuinely stopped moving at hop ${meta.depthReached}.`,
        complete: true,
      };
    default:
      return {
        headline: `Trace reached hop ${meta.depthReached}`,
        detail:
          "This trace predates the engine's termination accounting, so the reason it stopped was not recorded.",
        complete: false,
      };
  }
}

// A risk score under 0.5 (on the 0-100 display scale) rounds to a bare "0",
// which reads identically to a wallet the model never actually scored. Below
// 1 — but genuinely nonzero, i.e. not an exact 0 from the backend — show 2
// decimal places instead, so "computed a near-zero risk" stays visually
// distinct from "no signal at all". At or above 1 it's a whole number;
// nobody needs "42.37/100" on a dashboard.
export function formatRiskScore(score: number): string {
  if (score > 0 && score < 1) return score.toFixed(2);
  return String(Math.round(score));
}

// ── Single source of truth for risk-tier color ──────────────────────────────
// Every screen that shows a risk score (Risk Intelligence, Investigation,
// Cases, Deposit Watch) used to pick its own color independently — one keyed
// off the tier, one off raw score thresholds that didn't match the backend's
// own 0.30/0.60/0.85 boundaries, one hardcoded to red regardless of tier.
// The same wallet could legitimately show as "critical red" on one screen
// and "medium orange" on another for the exact same score. One map, used
// everywhere, keyed off the backend's own `risk_tier` string — never
// re-derived from the raw number.
export const RISK_TIER_COLOR: Record<string, string> = {
  critical: "var(--color-signal)",
  high: "var(--color-signal)",
  medium: "var(--color-primary)",
  low: "var(--color-accent)",
  unknown: "var(--color-muted-foreground)",
};

export function riskTierColor(tier: string | null | undefined): string {
  return RISK_TIER_COLOR[tier ?? ""] ?? RISK_TIER_COLOR["unknown"]!;
}

// ── Plain-English risk factor explanations ──────────────────────────────────
// The model's SHAP output ("SHAP: 2.644 (increases risk)") is correct but
// meaningless to a non-ML investigator: it names a raw feature column and a
// contribution number with no unit an investigator can act on. This maps
// each factor that actually surfaces in the top-5 (in practice a couple
// dozen of the model's 92 features) to what it means in the vocabulary an
// investigator already uses — collectors, layering, cash-out, victim
// deposits — instead of feature-column jargon. A feature not in this table
// (rare — mostly graph-embedding columns with no standalone real-world
// meaning) still gets a readable, if generic, fallback rather than breaking.
const FEATURE_STORY: Record<string, { increases: string; decreases: string }> = {
  total_txs: {
    increases:
      "This wallet has made an unusually high number of transactions overall — a pattern typical of automated layering rather than casual personal use.",
    decreases:
      "This wallet's overall transaction count is low, more consistent with normal, occasional use than an automated laundering pipeline.",
  },
  transacted_w_address_total: {
    increases:
      "This wallet has moved funds through an unusually large number of distinct counterparties — a hallmark of deliberately fragmenting money to obscure its trail.",
    decreases:
      "This wallet deals with a small, stable set of counterparties, not the sprawling fan-out typical of layering.",
  },
  transacted_w_address_max: {
    increases:
      "A single counterparty accounts for an unusually large share of this wallet's activity — consistent with a direct victim-to-collector or collector-to-cashout relationship.",
    decreases:
      "No single counterparty dominates this wallet's activity, more typical of ordinary use than a concentrated fraud flow.",
  },
  first_block_appeared_in: {
    increases:
      "This wallet is relatively new on-chain — freshly created wallets are disproportionately used to collect scam proceeds once, then get abandoned.",
    decreases:
      "This wallet has a long on-chain history predating the activity under investigation, more typical of a legitimate, established address.",
  },
  last_block_appeared_in: {
    increases:
      "This wallet's activity is very recent, consistent with a wallet still actively being used to move funds.",
    decreases:
      "This wallet has been inactive for a long stretch, which lowers the odds it's part of an ongoing, live laundering operation.",
  },
  value_transacted_mean: {
    increases:
      "The average size of this wallet's transactions is unusually high — a pattern seen in wallets consolidating or distributing large stolen sums.",
    decreases:
      "The average transaction size here is small and unremarkable, more consistent with routine, low-value activity than large-scale fund movement.",
  },
  value_transacted_total: {
    increases:
      "The total value that has passed through this wallet is unusually high for a wallet of this type.",
    decreases:
      "The total value that has passed through this wallet is modest and unremarkable.",
  },
  value_received_mean: {
    increases:
      "This wallet typically receives unusually large amounts per transaction — consistent with being a collection point for pooled victim funds.",
    decreases:
      "Amounts received per transaction are modest, not the large lump-sum deposits typical of a fraud collector wallet.",
  },
  value_received_max: {
    increases:
      "At least one very large single deposit landed in this wallet — the kind of lump sum seen when a victim's funds are paid in all at once.",
    decreases:
      "No unusually large single deposit stands out in this wallet's history.",
  },
  value_received_median: {
    increases:
      "Even the typical (median) deposit into this wallet runs unusually high.",
    decreases:
      "The typical deposit into this wallet is small, not the concentrated inflow pattern seen in fraud collection.",
  },
  value_sent_mean: {
    increases:
      "This wallet typically sends out unusually large amounts per transaction, consistent with bulk-moving pooled funds onward.",
    decreases: "Outgoing transaction sizes here are modest and unremarkable.",
  },
  value_sent_max: {
    increases:
      "At least one very large single outgoing payment left this wallet — consistent with moving a large pooled sum onward in one go.",
    decreases: "No unusually large single outgoing payment stands out.",
  },
  time_between_txs_mean: {
    increases:
      "Transactions from this wallet happen in unusually rapid succession — automated, scripted movement rather than manual, human-paced spending.",
    decreases:
      "Transactions from this wallet are spaced out normally, more consistent with manual, human-paced use than a scripted layering bot.",
  },
  time_between_output_txs_mean: {
    increases:
      "Outgoing transfers from this wallet fire off in rapid bursts, a signature of automated fund-forwarding.",
    decreases: "Outgoing transfers are spaced out at a normal, human pace.",
  },
  fee_ratio_max: {
    increases:
      "This wallet has paid an unusually high fee relative to transaction value at least once — sometimes seen when funds are rushed through regardless of cost.",
    decreases: "Fees paid relative to transaction value stay in a normal range.",
  },
  fee_ratio_mean: {
    increases:
      "This wallet consistently pays high fees relative to the amounts it moves.",
    decreases: "Fees paid relative to amounts moved are unremarkable.",
  },
  chain_fee_max: {
    increases:
      "This wallet has paid an unusually large network fee on at least one transaction — sometimes a sign of urgency to move funds quickly.",
    decreases: "Network fees paid are unremarkable.",
  },
  chain_fee_mean: {
    increases: "This wallet consistently pays high network fees.",
    decreases: "Network fees paid are typical.",
  },
  illicit_neighbor_ratio_1hop: {
    increases:
      "A meaningful share of this wallet's direct counterparties are themselves already flagged as illicit — guilt by direct association.",
    decreases:
      "Few or none of this wallet's direct counterparties are flagged as illicit.",
  },
  illicit_neighbor_ratio_2hop: {
    increases:
      "A meaningful share of wallets two hops away are flagged as illicit — this wallet sits close to known-bad activity in the transaction graph.",
    decreases:
      "Wallets two hops away show little connection to known-illicit activity.",
  },
  shortest_path_to_known_illicit: {
    increases:
      "This wallet sits only a few hops away from a wallet already confirmed illicit in the transaction graph.",
    decreases: "This wallet is graph-distant from any confirmed-illicit wallet.",
  },
  num_addr_transacted_multiple: {
    increases:
      "This wallet has repeat, ongoing relationships with several counterparties rather than one-off transfers — consistent with a sustained laundering relationship.",
    decreases:
      "This wallet mostly transacts once with each counterparty rather than maintaining repeat relationships.",
  },
  sanctions_interception: {
    increases:
      "This exact address appears on an official government sanctions list — the strongest and most direct risk signal available, independent of on-chain behavior.",
    decreases:
      "This exact address appears on an official government sanctions list — the strongest and most direct risk signal available, independent of on-chain behavior.",
  },
  victim_complaint_corroboration: {
    increases:
      "Independent victims have separately named this exact wallet in their complaints — real, direct evidence the behavioral model has no way to see on its own.",
    decreases:
      "Independent victims have separately named this exact wallet in their complaints — real, direct evidence the behavioral model has no way to see on its own.",
  },
};

// Coarse, investigator-facing strength label. Calibrated against the actual
// range of SHAP magnitudes this model produces in practice (roughly 0-2.6),
// not a generic 0-1 scale.
function shapMagnitudeWord(abs: number): string {
  if (abs >= 1.5) return "very strong";
  if (abs >= 0.8) return "strong";
  if (abs >= 0.4) return "moderate";
  return "slight";
}

function explainSignal(
  featureName: string,
  contribution: number,
  direction: "increases_risk" | "decreases_risk",
  backendDetail: string | null | undefined,
): { evidence: string; detail: string } {
  const increases = direction === "increases_risk";
  const mag = shapMagnitudeWord(Math.abs(contribution));
  const story = FEATURE_STORY[featureName];
  const prettyName = featureName.replace(/_/g, " ");

  const evidence = `${mag[0]!.toUpperCase()}${mag.slice(1)} signal — ${increases ? "raises" : "lowers"} this wallet's risk`;

  const plainEnglish =
    story?.[increases ? "increases" : "decreases"] ??
    `This wallet's "${prettyName}" measurement is unusual enough to be a ${mag} ${increases ? "risk-raising" : "risk-lowering"} factor in the model, though this specific feature doesn't yet have a plain-language description on file.`;

  // For a sanctions hit, the backend's own designation text (organization,
  // list, program codes) IS the real evidence — lead with it, not the
  // generic sentence. For everything else it's a technical aside for anyone
  // who wants the raw number behind the plain-English summary.
  const detail =
    featureName === "sanctions_interception" && backendDetail
      ? `${plainEnglish} Designation: ${backendDetail}.`
      : `${plainEnglish} (Model detail: this factor contributed ${contribution.toFixed(3)} to the underlying risk calculation, ${increases ? "pushing it up" : "pulling it down"}.)`;

  return { evidence, detail };
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
        // Never coerce an unscoreable wallet into a number. `null * 100` is 0,
        // which displayed as "0/100" — reading as "checked and completely
        // clean" for a wallet the engine explicitly could not score.
        //
        // Kept to 2 decimal places on the 0-100 scale rather than rounded to
        // a whole number: a genuinely low-risk wallet can score e.g. 0.03,
        // and Math.round collapsed that (and everything else under 0.5) down
        // to a flat "0" indistinguishable from a wallet with zero signal at
        // all. The UI formats this back down to a whole number when it's not
        // near zero — see formatScore in risk.tsx.
        setRiskScore(
          data.risk_score === null || data.risk_score === undefined
            ? null
            : Math.round(toNum(data.risk_score) * 100 * 100) / 100,
        );
        setRiskTier(data.risk_tier);
        setSignals(
          data.evidence.map((ev, i) => {
            const { evidence, detail } = explainSignal(
              ev.feature_name,
              ev.contribution,
              ev.direction,
              ev.detail,
            );
            return {
              id: `ev${i}`,
              label: ev.feature_name
                .replace(/_/g, " ")
                .replace(/\b\w/g, (c) => c.toUpperCase()),
              contribution: Math.max(1, Math.round(Math.abs(ev.contribution) * 30)),
              direction: ev.direction,
              evidence,
              dataSource:
                ev.feature_name === "sanctions_interception"
                  ? "OFAC Sanctions List (SDN)"
                  : ev.feature_name === "victim_complaint_corroboration"
                    ? "NCRP / Sahyog Complaint Records"
                    : "XGBoost / Elliptic++ Dataset",
              detail,
            };
          }),
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
