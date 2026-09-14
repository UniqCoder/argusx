import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useMemo } from "react";
import { type TraceNode, type TraceEdge } from "@/lib/mock-data";
import { useCaseContext } from "@/store/case-context-store";
import {
  useWalletTrace,
  useWalletRisk,
  formatRiskScore,
  riskTierColor,
  terminalExplanation,
  terminationSummary,
  type TraceMeta,
} from "@/hooks/use-wallet";
import { useCorrelation, type NetworkSignal } from "@/hooks/use-correlation";
import { useTraceLayout } from "@/hooks/use-trace-layout";
import { useTraceTimeline } from "@/hooks/use-trace-timeline";
import { TraceGraph } from "@/components/dashboard/TraceGraph";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import type { Chain, Complaint } from "@/lib/api-types";
import { formatAmount } from "@/lib/decimal";
import { truncateAddress } from "@/lib/address";
import { computeEvidenceStrength } from "@/lib/evidence";

export const Route = createFileRoute("/dashboard/investigation")({
  component: InvestigationWorkspace,
});

const MONO = "var(--font-mono)";

// ─── Playback controls ───────────────────────────────────────────────────────
function TraceControls({
  playing,
  onPlayPause,
  speed,
  onSpeed,
  progress,
  onScrub,
  stepIndex,
  stepCount,
  onStepBack,
  onStepForward,
}: {
  playing: boolean;
  onPlayPause: () => void;
  speed: number;
  onSpeed: (s: number) => void;
  progress: number;
  onScrub: (v: number) => void;
  stepIndex: number;
  stepCount: number;
  onStepBack: () => void;
  onStepForward: () => void;
}) {
  // Step position, independent of whether a transfer is mid-flight — used to
  // disable Prev/Next at the two ends so a click there is a deliberate no-op
  // rather than silently doing nothing. `progress > 0` at stepIndex 0 means a
  // transfer is already in flight out of the root, so Prev is still live.
  const atStart = stepIndex === 0 && progress === 0;
  const atEnd = stepIndex >= stepCount && progress >= 1;
  return (
    <div className="ug-trace-controls">
      <button
        className="ug-btn-ghost"
        onClick={() => onScrub(0)}
        style={{ padding: "0.3rem 0.75rem", fontSize: "0.68rem", borderRadius: 2 }}
      >
        ↺ Replay
      </button>
      <button
        className="ug-btn-ghost"
        onClick={onStepBack}
        disabled={stepCount === 0 || atStart}
        title="Previous transfer"
        style={{ padding: "0.3rem 0.6rem", fontSize: "0.68rem", borderRadius: 2 }}
      >
        ⏮ Prev
      </button>
      <button
        className="ug-btn-ghost"
        onClick={onPlayPause}
        disabled={stepCount === 0}
        style={{ padding: "0.3rem 0.9rem", fontSize: "0.68rem", borderRadius: 2 }}
      >
        {playing ? "⏸ Pause" : "▶ Play"}
      </button>
      <button
        className="ug-btn-ghost"
        onClick={onStepForward}
        disabled={stepCount === 0 || atEnd}
        title="Next transfer"
        style={{ padding: "0.3rem 0.6rem", fontSize: "0.68rem", borderRadius: 2 }}
      >
        Next ⏭
      </button>

      <div style={{ display: "flex", gap: 2 }}>
        {[1, 2, 4].map((s) => (
          <button
            key={s}
            onClick={() => onSpeed(s)}
            style={{
              padding: "0.25rem 0.6rem",
              borderRadius: 2,
              fontFamily: MONO,
              fontSize: "0.62rem",
              background: speed === s ? "oklch(0.83 0.14 205 / 16%)" : "transparent",
              border:
                speed === s
                  ? "1px solid oklch(0.83 0.14 205 / 40%)"
                  : "1px solid var(--border-strong)",
              color: speed === s ? "var(--color-accent)" : "var(--color-muted-foreground)",
              cursor: "pointer",
            }}
          >
            {s}×
          </button>
        ))}
      </div>

      <div style={{ flex: 1, display: "flex", alignItems: "center", gap: "0.75rem" }}>
        {/* Counts TRANSFERS, not nodes. The old readout said "Hop N / total
            nodes", which conflated two different things and overstated depth
            (a 40-node/3-hop trace read as "Hop 40 / 40"). */}
        <span
          style={{
            fontFamily: MONO,
            fontSize: "0.6rem",
            color: "var(--color-muted-foreground)",
            whiteSpace: "nowrap",
          }}
        >
          {stepCount === 0
            ? "No transfers to replay"
            : `Transfer ${Math.min(stepIndex + (progress > 0 ? 1 : 0), stepCount)} / ${stepCount}`}
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.002}
          value={progress}
          disabled={stepCount === 0}
          onChange={(e) => onScrub(parseFloat(e.target.value))}
          style={{ flex: 1, accentColor: "var(--color-accent)", height: 3, cursor: "pointer" }}
        />
      </div>
    </div>
  );
}

// ─── Trace provenance / honesty panel ───────────────────────────────────────
// Answers, without being asked: how deep did this actually go, why did it stop,
// what was it seeded with, and what did it deliberately not follow. Before
// this, a trace that resolved 3 of 8 requested hops and discarded 21 branches
// below the dust floor was presented identically to a complete one.
function TraceProvenance({ meta }: { meta: TraceMeta }) {
  const summary = terminationSummary(meta);
  const accent = summary.complete ? "var(--color-accent)" : "var(--color-signal)";
  return (
    <div style={{ marginTop: "0.75rem" }}>
      <p className="ug-section-title">Trace Provenance</p>
      <div
        style={{
          padding: "0.6rem 0.7rem",
          background: summary.complete
            ? "oklch(0.83 0.14 205 / 6%)"
            : "oklch(0.79 0.15 74 / 7%)",
          border: `1px solid ${summary.complete ? "oklch(0.83 0.14 205 / 22%)" : "oklch(0.79 0.15 74 / 26%)"}`,
          borderLeft: `2px solid ${accent}`,
          borderRadius: 2,
          marginBottom: "0.6rem",
        }}
      >
        <p
          style={{
            fontFamily: MONO,
            fontSize: "0.6rem",
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: accent,
            marginBottom: "0.35rem",
          }}
        >
          {summary.headline}
        </p>
        <p
          style={{
            fontSize: "0.7rem",
            color: "var(--color-muted-foreground)",
            lineHeight: 1.6,
          }}
        >
          {summary.detail}
        </p>
      </div>

      {[
        { k: "Asset traced", v: `${meta.asset} (${meta.assetBasis.replace(/_/g, " ")})` },
        {
          k: "Tainted seed",
          v: `${formatAmount(meta.seedValue, meta.asset)} · ${meta.seedBasis.replace(/_/g, " ")}`,
        },
        { k: "Depth", v: `${meta.depthReached} reached / ${meta.depthRequested} requested` },
        { k: "Addresses", v: String(meta.nodeCount) },
        ...(meta.prunedBranchCount
          ? [
              {
                k: "Below dust floor",
                v: `${meta.prunedBranchCount} branches (${formatAmount(meta.prunedBranchValue, meta.asset)})`,
              },
            ]
          : []),
        ...(meta.otherAssetBranchCount
          ? [{ k: "Other-asset outflow", v: `${meta.otherAssetBranchCount} transfers not traced` }]
          : []),
        ...(meta.orphanedEdges
          ? [{ k: "Dropped edges", v: `${meta.orphanedEdges} (endpoint missing)` }]
          : []),
      ].map(({ k, v }) => (
        <div key={k} className="ug-data-row">
          <span className="ug-data-row__key">{k}</span>
          <span className="ug-data-row__value" style={{ fontSize: "0.7rem" }}>
            {v}
          </span>
        </div>
      ))}
    </div>
  );
}

// ─── Intelligence Inspector ─────────────────────────────────────────────────
function IntelligenceInspector({
  selectedId,
  nodes,
  edges,
  meta,
  correlationSignal,
  linkedComplaints,
  targetAddress,
  riskTier,
}: {
  selectedId: string | null;
  nodes: TraceNode[];
  edges: TraceEdge[];
  meta: TraceMeta | null;
  correlationSignal: NetworkSignal | null;
  linkedComplaints: Complaint[];
  targetAddress: string | null;
  riskTier: string | null;
}) {
  const node = nodes.find((n) => n.id === selectedId);
  const edge = edges.find((e) => e.id === selectedId);
  const asset = meta?.asset ?? "";

  if (!selectedId) {
    return (
      <div style={{ padding: "1.25rem" }}>
        <p
          style={{
            fontSize: "0.78rem",
            color: "var(--color-muted-foreground)",
            lineHeight: 1.6,
          }}
        >
          Select a wallet node or a transfer to inspect the evidence behind it.
        </p>
      </div>
    );
  }

  if (node) {
    const why = terminalExplanation(node, asset);
    const isPayoff = node.terminalKind === "VASP" || node.terminalKind === "NO_OUTFLOW";
    const isVictim = node.type === "victim";
    const isFraudster = !!node.isSuspectedFraudster;

    // First/last filing dates across the complaints that actually name this
    // wallet — real dates from real complaints, not a fabricated range.
    const filedDates = linkedComplaints
      .map((c) => c.filed_at)
      .filter((d): d is string => !!d)
      .sort();
    const firstObserved = filedDates[0];
    const lastObserved = filedDates[filedDates.length - 1];

    return (
      <div style={{ padding: "1.25rem" }}>
        <p
          style={{
            fontFamily: MONO,
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: isFraudster ? "var(--color-signal)" : "var(--color-accent)",
            marginBottom: "0.5rem",
          }}
        >
          {isVictim
            ? "Victim"
            : isFraudster
              ? "Suspected Fraudster"
              : (node.entity ?? node.type)}
        </p>
        <h3
          style={{
            fontSize: "0.92rem",
            fontWeight: 700,
            color: "var(--color-foreground)",
            marginBottom: "1rem",
          }}
        >
          {node.label}
        </h3>

        {(isVictim
          ? [
              { k: "Location", v: node.address },
              ...(node.amount ? [{ k: "Amount lost", v: node.amount }] : []),
              ...(node.firstTaintedAt
                ? [{ k: "Filed", v: new Date(node.firstTaintedAt).toLocaleDateString() }]
                : []),
              ...(targetAddress
                ? [{ k: "Reported wallet", v: truncateAddress(targetAddress) }]
                : []),
            ]
          : [
              { k: "Address", v: node.address },
              { k: "Chain", v: node.blockchain },
              { k: "Hop", v: node.hop != null ? String(node.hop) : "—" },
              { k: "Received", v: node.amount ?? "—" },
              ...(node.terminalKind ? [{ k: "Terminal", v: node.terminalKind }] : []),
            ]
        ).map(({ k, v }) => (
          <div key={k} className="ug-data-row">
            <span className="ug-data-row__key">{k}</span>
            <span
              className="ug-data-row__value"
              style={{ fontFamily: k === "Address" ? MONO : undefined }}
            >
              {v}
            </span>
          </div>
        ))}

        {/* Every dead end explains itself. An unexplained stop is
            indistinguishable from a bug. */}
        {why && (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              background: isPayoff
                ? "oklch(0.79 0.15 74 / 8%)"
                : "oklch(0.98 0 0 / 3%)",
              border: `1px solid ${isPayoff ? "oklch(0.79 0.15 74 / 28%)" : "var(--border-subtle)"}`,
              borderRadius: 2,
            }}
          >
            <p
              style={{
                fontFamily: MONO,
                fontSize: "0.58rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: isPayoff ? "var(--color-primary)" : "var(--color-muted-foreground)",
                marginBottom: "0.4rem",
              }}
            >
              Why the trail stops here
            </p>
            <p style={{ fontSize: "0.74rem", lineHeight: 1.65, color: "var(--color-foreground)" }}>
              {why}
            </p>
          </div>
        )}

        {(node.prunedChildCount || node.otherAssetChildCount) && (
          <div style={{ marginTop: "0.75rem" }}>
            {node.prunedChildCount ? (
              <div className="ug-data-row">
                <span className="ug-data-row__key">Branches below dust</span>
                <span className="ug-data-row__value">
                  {node.prunedChildCount}
                  {node.prunedChildValue
                    ? ` (${formatAmount(node.prunedChildValue, asset)})`
                    : ""}
                </span>
              </div>
            ) : null}
            {node.otherAssetChildCount ? (
              <div className="ug-data-row">
                <span className="ug-data-row__key">Other-asset transfers</span>
                <span className="ug-data-row__value">{node.otherAssetChildCount}</span>
              </div>
            ) : null}
          </div>
        )}

        {/* Why ARGUS flagged this wallet — every field here is a real number
            already computed by useCorrelation/useWalletRisk for this same
            wallet (the same numbers Cross-Victim, Network Signals and Risk
            Intelligence show), never a separate calculation. Evidence
            strength combines BOTH independent signals (victim correlation +
            the ML risk tier) — see src/lib/evidence.ts for the exact,
            documented thresholds; it's never a bare "High Risk" label with
            nothing behind it. */}
        {isFraudster && correlationSignal && (() => {
          const evidence = computeEvidenceStrength({
            correlationScore: correlationSignal.correlationScore,
            riskTier,
          });
          return (
          <div
            style={{
              marginTop: "1rem",
              padding: "0.75rem",
              background: "oklch(0.64 0.22 18 / 8%)",
              border: "1px solid oklch(0.64 0.22 18 / 28%)",
              borderRadius: 2,
            }}
          >
            <p
              style={{
                fontFamily: MONO,
                fontSize: "0.58rem",
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--color-signal)",
                marginBottom: "0.5rem",
              }}
            >
              Why flagged
            </p>
            <p style={{ fontSize: "0.72rem", lineHeight: 1.6, color: "var(--color-foreground)", marginBottom: "0.4rem" }}>
              {correlationSignal.victims} independent victim
              {correlationSignal.victims === 1 ? "" : "s"} filed complaints
              naming this wallet, across {correlationSignal.states} state
              {correlationSignal.states === 1 ? "" : "s"}.
            </p>
            <ul style={{ margin: "0 0 0.6rem", paddingLeft: "1rem" }}>
              {evidence.reasons.map((r) => (
                <li key={r} style={{ fontSize: "0.68rem", color: "var(--color-muted-foreground)", lineHeight: 1.6 }}>
                  {r}
                </li>
              ))}
            </ul>
            {[
              { k: "Connected victims", v: String(correlationSignal.victims) },
              { k: "Relevant complaints", v: String(correlationSignal.complaints) },
              { k: "Total relevant flow", v: correlationSignal.totalFundsAtRisk },
              ...(firstObserved
                ? [{ k: "First observed", v: new Date(firstObserved).toLocaleDateString() }]
                : []),
              ...(lastObserved && lastObserved !== firstObserved
                ? [{ k: "Last observed", v: new Date(lastObserved).toLocaleDateString() }]
                : []),
              ...(riskTier ? [{ k: "ML risk tier", v: riskTier.toUpperCase() }] : []),
              { k: "Evidence strength", v: evidence.strength },
            ].map(({ k, v }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span className="ug-data-row__value" style={{ fontSize: "0.7rem" }}>
                  {v}
                </span>
              </div>
            ))}
          </div>
          );
        })()}

        <div className="ug-divider" />
        <p style={{ fontFamily: MONO, fontSize: "0.6rem", color: "var(--color-muted-foreground)", lineHeight: 1.6 }}>
          Per-wallet ML risk scoring lives on the Risk Intelligence page — the
          trace engine classifies terminals, it does not score every hop.
        </p>
      </div>
    );
  }

  if (edge) {
    const fromNode = nodes.find((n) => n.id === edge.from);
    const toNode = nodes.find((n) => n.id === edge.to);
    return (
      <div style={{ padding: "1.25rem" }}>
        <p
          style={{
            fontFamily: MONO,
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--color-accent)",
            marginBottom: "1rem",
          }}
        >
          Transfer Evidence
        </p>
        {[
          { k: "From", v: fromNode?.label ?? edge.from },
          { k: "To", v: toNode?.label ?? edge.to },
          { k: "Amount", v: edge.amount },
          { k: "When", v: edge.timestamp ? new Date(edge.timestamp).toLocaleString() : "—" },
          { k: "Source", v: edge.dataSource },
        ].map(({ k, v }) => (
          <div key={k} className="ug-data-row">
            <span className="ug-data-row__key">{k}</span>
            <span className="ug-data-row__value">{v}</span>
          </div>
        ))}
        {edge.txHash && (
          <>
            <div className="ug-divider" />
            <p className="ug-section-title">Transaction Hash</p>
            <p
              style={{
                fontFamily: MONO,
                fontSize: "0.66rem",
                color: "var(--color-accent)",
                wordBreak: "break-all",
                lineHeight: 1.5,
              }}
            >
              {edge.txHash}
            </p>
            <p
              style={{
                fontSize: "0.66rem",
                color: "var(--color-muted-foreground)",
                marginTop: "0.5rem",
                lineHeight: 1.6,
              }}
            >
              This hash is the evidence — it is verifiable on any public
              explorer, independently of ARGUS.
            </p>
          </>
        )}
      </div>
    );
  }

  return null;
}

// ─── Workspace ──────────────────────────────────────────────────────────────
function InvestigationWorkspace() {
  const navigate = useNavigate();
  const { activeWallet, activeChain, activeCaseNumber, activeCaseStatus } =
    useCaseContext();
  const chain = (activeChain || "ETH") as Chain;

  const [traceRetryKey, setTraceRetryKey] = useState(0);

  const {
    nodes: rawNodes,
    edges,
    meta,
    vasp,
    loading: traceLoading,
    progress: traceProgress,
    error: traceError,
  } = useWalletTrace(activeWallet, chain, traceRetryKey);

  const {
    riskScore,
    riskTier,
    signals: riskSignals,
    error: riskError,
    loading: riskLoading,
  } = useWalletRisk(activeWallet, chain);
  const { signal: correlationSignal, linkedComplaints } = useCorrelation(
    activeWallet,
    chain,
  );

  // Real victim/complaint nodes, from the same correlation data the
  // Cross-Victim page reads — never fabricated, and only added when a real
  // complaint actually names this wallet. Injected at hop -1 so they draw
  // one layer BEFORE the target, per VICTIM -> TARGET WALLET. Capped so a
  // wallet named by dozens of complaints doesn't turn the graph into a wall
  // of nodes; the true count is already the headline number on Cross-Victim.
  const targetId = rawNodes.find((n) => n.isTarget)?.id;
  const MAX_VICTIM_NODES = 4;
  const victimNodes: TraceNode[] = useMemo(() => {
    if (!targetId || linkedComplaints.length === 0) return [];
    return linkedComplaints.slice(0, MAX_VICTIM_NODES).map((c) => ({
      id: `victim-${c.id}`,
      type: "victim" as const,
      label: c.ncrp_ref ? `NCRP ${c.ncrp_ref.slice(-6)}` : "Complaint",
      address: c.state ?? "Location unknown",
      blockchain: chain,
      hop: -1,
      resolved: true,
      // Real complaint fields, reused via the existing amount/firstTaintedAt
      // slots rather than adding new ones, so the evidence inspector can
      // show what was actually lost and when without fabricating anything.
      ...(c.amount_lost != null
        ? { amount: `₹${c.amount_lost.toLocaleString("en-IN")}` }
        : {}),
      firstTaintedAt: c.filed_at,
      x: 0,
      y: 0,
    }));
  }, [linkedComplaints, targetId, chain]);
  const victimEdges: TraceEdge[] = useMemo(() => {
    if (!targetId) return [];
    return victimNodes.map((v) => ({
      id: `${v.id}-${targetId}`,
      from: v.id,
      to: targetId,
      // Distinguishes a "this wallet was reported" relationship from a real
      // money transfer, both for styling and so the causal replay timeline
      // (built below from the untouched, real trace edges) never mistakes
      // it for a transaction with a fabricated amount/timestamp.
      method: "victim_report",
      amount: "—",
      timestamp: "",
      dataSource: "NCRP complaint",
      resolved: true,
    }));
  }, [victimNodes, targetId]);
  const victimNodeIds = useMemo(
    () => new Set(victimNodes.map((v) => v.id)),
    [victimNodes],
  );
  const victimEdgeIds = useMemo(
    () => new Set(victimEdges.map((e) => e.id)),
    [victimEdges],
  );

  // Evidence controls the label, not a guess: the target only becomes a
  // "suspected fraudster" when real evidence backs it — a linked complaint
  // (victimNodes is built from actual `linkedComplaints`, never fabricated)
  // OR a CRITICAL risk tier, which as of the corroboration-gated scoring in
  // risk_service.py now itself requires real backing (2+ independent
  // complaints, an OFAC sanctions match, or a model score so extreme it's
  // corroborating itself) rather than one middling feature swing. Absent
  // either, it stays a neutral "reported wallet" — being traced is not the
  // same as being confirmed a fraudster.
  const hasVictimEvidence = victimNodes.length > 0;
  const hasStrongRiskEvidence = riskTier === "critical";
  // Combined evidence strength — see src/lib/evidence.ts for the documented
  // thresholds. Computed once here so the summary strip, the glance chip and
  // the fraudster inspector panel never disagree with each other.
  const evidence = correlationSignal
    ? computeEvidenceStrength({
        correlationScore: correlationSignal.correlationScore,
        riskTier,
      })
    : null;
  const nodesForLayout = useMemo(() => {
    const nodes = [...victimNodes, ...rawNodes];
    if ((!hasVictimEvidence && !hasStrongRiskEvidence) || !targetId) return nodes;
    return nodes.map((n) =>
      n.id === targetId ? { ...n, isSuspectedFraudster: true } : n,
    );
  }, [victimNodes, rawNodes, hasVictimEvidence, hasStrongRiskEvidence, targetId]);
  const edgesForLayout = useMemo(
    () => [...victimEdges, ...edges],
    [victimEdges, edges],
  );

  const layout = useTraceLayout(nodesForLayout, edgesForLayout);
  const nodes = layout.nodes;
  // The replay clock is built from the REAL trace only — the victim/complaint
  // link is a reporting relationship, not a transaction, so it must never
  // enter the "transfer N of M" chronology. It's added back below as an
  // always-visible edge instead.
  const timeline = useTraceTimeline(rawNodes, edges);

  const explorerUnavailable = nodes.some(
    (n) => n.terminalKind === "EXPLORER_UNAVAILABLE",
  );

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [progress, setProgress] = useState(0);
  const [showDiagnostics, setShowDiagnostics] = useState(false);

  // A brand-new wallet/chain clears playback along with the graph.
  useEffect(() => {
    setProgress(0);
    setPlaying(false);
    setSelectedId(null);
  }, [activeWallet, chain, traceRetryKey]);

  // Auto-play the chronological reconstruction once the trace finishes —
  // not on every intermediate streamed node. `timeline` gets a new identity
  // on every one of the (up to ~75) nodes a trace streams in, so depending on
  // it here restarted playback from 0 dozens of times per trace instead of
  // once. `traceLoading` only flips twice (true -> false), which is what
  // "once per completed trace" actually means.
  useEffect(() => {
    if (!traceLoading && timeline.steps.length > 0) {
      setProgress(0);
      setPlaying(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [traceLoading]);

  // The one clock. Pace is per-transfer, not a flat 17s for every trace:
  // a 3-transfer trace used to crawl at the same rate as a 70-transfer one.
  // Depends on the step COUNT, not the `timeline` object itself, so this
  // interval isn't torn down and recreated on every streamed node while a
  // trace is still loading — only when the count actually changes.
  const stepCount = timeline.steps.length;
  useEffect(() => {
    if (!playing) return;
    const steps = Math.max(1, stepCount);
    const msPerStep = 620 / speed;
    const tickMs = 40;
    const delta = tickMs / (msPerStep * steps);
    const id = setInterval(() => {
      setProgress((p) => {
        const next = p + delta;
        if (next >= 1) {
          setPlaying(false);
          return 1;
        }
        return next;
      });
    }, tickMs);
    return () => clearInterval(id);
  }, [playing, speed, stepCount]);

  const realFrame = timeline.frameAt(progress);
  // Victim/complaint nodes and their report-link edges are always visible —
  // they aren't part of the money-trail replay, so they don't wait for a
  // playback position to "arrive".
  const frame = useMemo(
    () => ({
      ...realFrame,
      revealedNodes: victimNodeIds.size
        ? new Set([...realFrame.revealedNodes, ...victimNodeIds])
        : realFrame.revealedNodes,
      revealedEdges: victimEdgeIds.size
        ? new Set([...realFrame.revealedEdges, ...victimEdgeIds])
        : realFrame.revealedEdges,
    }),
    [realFrame, victimNodeIds, victimEdgeIds],
  );

  // Step exactly one transfer forward/back, snapped to a step boundary —
  // instead of re-pressing Play (which always restarts the interval from
  // wherever `progress` happens to sit) or dragging the scrub bar (which
  // lands mid-transfer as often as not). `frame.stepIndex` is how many
  // transfers are already fully settled at the current `progress`, so ±1
  // step lands exactly on "N transfers complete", never a fraction of one.
  const handleStep = (delta: 1 | -1) => {
    setPlaying(false);
    if (stepCount === 0) return;
    const target = Math.max(0, Math.min(stepCount, frame.stepIndex + delta));
    setProgress(target / stepCount);
  };

  // A meaningful, live status line instead of a flat QUERYING/REPLAYING/
  // PAUSED — every state below comes from a real signal already computed
  // above (the engine's own progress counter while streaming, or which real
  // terminal kind the active transfer is landing on during replay). Nothing
  // here is a fabricated event.
  const activeDestination = frame.active
    ? nodes.find((n) => n.id === frame.active!.step.toId)
    : undefined;
  const traceStatusText = traceLoading
    ? traceProgress
      ? `RESOLVING HOP ${traceProgress.hop}`
      : "INITIALIZING TRACE"
    : activeDestination?.terminalKind === "VASP"
      ? "EXCHANGE PROXIMITY DETECTED"
      : activeDestination?.terminalKind === "BRIDGE"
        ? "BRIDGE DETECTED"
        : activeDestination?.terminalKind === "MIXER_BOUNDARY"
          ? "MIXER EXPOSURE DETECTED"
          : playing
            ? "FOLLOWING FUNDS"
            : frame.stepCount > 0 && progress >= 1
              ? "TRACE COMPLETE"
              : frame.stepCount === 0 && nodes.length > 0
                ? "TRACE COMPLETE"
                : "PAUSED";

  if (!activeWallet) {
    return (
      <div className="ug-surface" style={{ padding: "1.5rem" }}>
        <p style={{ fontFamily: MONO, fontSize: "0.68rem", color: "var(--color-muted-foreground)" }}>
          No wallet selected — go to Trace Wallet and paste an address to start
          an investigation.
        </p>
      </div>
    );
  }

  const singleNodeTerminal =
    nodes.length === 1 && !traceLoading ? nodes[0]?.terminalKind : undefined;

  return (
    <div
      className="ug-workspace"
      style={{ margin: "-2rem -2.25rem", height: "calc(100vh - 48px)" }}
    >
      {/* ── Center: the money trail ── */}
      <div className="ug-workspace__center">
        <div
          style={{
            padding: "0.75rem 1.25rem",
            borderBottom: "1px solid var(--border-strong)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <p className="ug-section-title" style={{ marginBottom: 0 }}>
            Money Trail
            {meta ? (
              <span style={{ color: "var(--color-muted-foreground)", fontWeight: 400 }}>
                {"  ·  "}
                {meta.asset}
              </span>
            ) : null}
          </p>
          <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
            <span className="ug-system-live__dot" />
            {traceStatusText}
          </div>
        </div>

        {/* Compact investigation summary — only when there's a real finding
            to summarize (at least one victim complaint names this wallet).
            Not another dashboard: one row, real numbers already computed
            above (correlationSignal, linkedComplaints), nothing fabricated. */}
        {hasVictimEvidence && correlationSignal && (
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "1.5rem",
              padding: "0.6rem 1.25rem",
              borderBottom: "1px solid var(--border-strong)",
              background: "oklch(0.64 0.22 18 / 5%)",
            }}
          >
            {[
              {
                k: "Victim" + (correlationSignal.victims === 1 ? "" : "s"),
                v: String(correlationSignal.victims),
              },
              {
                k: "Suspected fraudster",
                v: activeWallet ? truncateAddress(activeWallet) : "—",
              },
              {
                k: "Relationship",
                v: `${correlationSignal.complaints} complaint${correlationSignal.complaints === 1 ? "" : "s"} name this wallet`,
              },
              { k: "Relevant flow", v: correlationSignal.totalFundsAtRisk },
              { k: "Evidence", v: evidence?.strength ?? correlationSignal.signalStrength },
            ].map(({ k, v }) => (
              <div key={k}>
                <p
                  style={{
                    fontFamily: MONO,
                    fontSize: "0.52rem",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    color: "var(--color-muted-foreground)",
                    marginBottom: "0.15rem",
                  }}
                >
                  {k}
                </p>
                <p
                  style={{
                    fontFamily: MONO,
                    fontSize: "0.7rem",
                    color: "var(--color-foreground)",
                  }}
                >
                  {v}
                </p>
              </div>
            ))}
          </div>
        )}

        {/* A seeded case must never be able to look like a live one. The
            engine asserts this on the trace result; nothing here infers it. */}
        {meta && meta.dataSource !== "live" && (
          <div
            style={{
              padding: "0.5rem 1.25rem",
              background: "oklch(0.79 0.15 74 / 14%)",
              borderBottom: "1px solid oklch(0.79 0.15 74 / 40%)",
              display: "flex",
              alignItems: "center",
              gap: "0.6rem",
            }}
          >
            <span
              className="ug-badge"
              style={{
                fontSize: "0.55rem",
                background: "oklch(0.79 0.15 74 / 22%)",
                color: "var(--color-primary)",
                border: "1px solid oklch(0.79 0.15 74 / 50%)",
              }}
            >
              {meta.dataSource === "mixed" ? "PARTLY SEEDED" : "SEEDED SCENARIO"}
            </span>
            <span
              style={{
                fontFamily: MONO,
                fontSize: "0.62rem",
                color: "var(--color-primary)",
              }}
            >
              {meta.dataSource === "mixed"
                ? "Part of this trail came from seeded scenario data and part from live explorers."
                : "Seeded scenario — synthetic addresses and transactions, traced by the real engine. Not live blockchain data."}
            </span>
          </div>
        )}

        {/* Live engine readout. The trace used to be a single blocking request
            with no feedback, so a trace 80% done looked exactly like one that
            had hung. These counters come from the engine itself as it settles
            each node — they are measurements, not an animated placeholder. */}
        {traceLoading && traceProgress && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "1rem",
              flexWrap: "wrap",
              padding: "0.45rem 1.25rem",
              borderBottom: "1px solid var(--color-border)",
              background: "oklch(0.98 0 0 / 2.5%)",
              fontFamily: MONO,
              fontSize: "0.6rem",
              letterSpacing: "0.08em",
              color: "var(--color-muted-foreground)",
            }}
          >
            <span style={{ color: "var(--color-primary)" }}>
              HOP {traceProgress.hop}
            </span>
            <span>{traceProgress.nodes_settled} WALLETS MAPPED</span>
            <span>{traceProgress.frontier_size} QUEUED</span>
            <span>
              FOLLOWING {formatAmount(traceProgress.value_following, traceProgress.asset)}
            </span>
          </div>
        )}

        <div className="ug-trace-canvas" style={{ position: "relative" }}>
          {nodes.length === 0 ? (
            <div style={{ maxWidth: 460, margin: "3rem auto 0", textAlign: "center" }}>
              <p
                style={{
                  fontFamily: MONO,
                  fontSize: "0.68rem",
                  color: "var(--color-muted-foreground)",
                  lineHeight: 1.7,
                }}
              >
                {traceLoading
                  ? `Opening the trail on ${
                      chain === "TRON" ? "Tronscan" : chain === "BTC" ? "Blockstream" : "Blockscout"
                    } — the first wallet appears as soon as the engine settles it.`
                  : traceError
                    ? "Trace failed — see the error on the left."
                    : "No trace data for this wallet yet."}
              </p>
            </div>
          ) : singleNodeTerminal &&
            ["NO_OUTFLOW", "VASP", "MIXER_BOUNDARY", "BRIDGE"].includes(
              singleNodeTerminal,
            ) ? (
            /* A one-node result is a real answer, not an empty graph — but only
               if it says which answer. This previously only handled NO_OUTFLOW,
               so a wallet that IS a known exchange (the engine's own BTC
               example) rendered as a single unexplained dot. */
            <div style={{ maxWidth: 460, margin: "3rem auto 0", textAlign: "center", padding: "1.5rem" }}>
              <p
                style={{
                  fontFamily: MONO,
                  fontSize: "0.62rem",
                  letterSpacing: "0.2em",
                  textTransform: "uppercase",
                  color: "var(--color-accent)",
                  marginBottom: "0.75rem",
                }}
              >
                {singleNodeTerminal === "VASP"
                  ? `Trace complete — this address is a known ${nodes[0]?.entity ?? "VASP"}`
                  : singleNodeTerminal === "MIXER_BOUNDARY"
                    ? "Trace complete — this address is a known mixer"
                    : singleNodeTerminal === "BRIDGE"
                      ? "Trace complete — this address is a known bridge"
                      : "Trace complete — no outgoing activity found"}
              </p>
              <p style={{ fontSize: "0.8rem", color: "var(--color-muted-foreground)", lineHeight: 1.7 }}>
                {nodes[0] ? terminalExplanation(nodes[0], meta?.asset ?? chain) : ""}
              </p>
              {singleNodeTerminal === "VASP" && (
                <p
                  style={{
                    fontSize: "0.74rem",
                    color: "var(--color-muted-foreground)",
                    lineHeight: 1.7,
                    marginTop: "0.75rem",
                  }}
                >
                  The trace stops at hop 0 because the searched address is
                  itself the off-ramp — there is no upstream trail to follow
                  from here. To trace funds INTO this exchange, search the
                  victim's wallet instead.
                </p>
              )}
            </div>
          ) : (
            <>
              {explorerUnavailable && !traceLoading && (
                <div
                  style={{
                    position: "absolute",
                    top: "0.75rem",
                    left: "50%",
                    transform: "translateX(-50%)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                    padding: "0.5rem 0.85rem",
                    background: "oklch(0.79 0.15 74 / 10%)",
                    border: "1px solid oklch(0.79 0.15 74 / 40%)",
                    borderRadius: 2,
                    zIndex: 5,
                  }}
                >
                  <span style={{ fontFamily: MONO, fontSize: "0.62rem", color: "var(--color-foreground)" }}>
                    Explorer temporarily unavailable — this trace is incomplete.
                  </span>
                  <button
                    className="ug-btn-ghost"
                    onClick={() => setTraceRetryKey((k) => k + 1)}
                    style={{ padding: "0.25rem 0.75rem", fontSize: "0.62rem", borderRadius: 2 }}
                  >
                    ↺ Retry
                  </button>
                </div>
              )}
              <TraceGraph
                nodes={nodes}
                edges={edgesForLayout}
                frame={frame}
                contentWidth={layout.width}
                contentHeight={layout.height}
                selectedId={selectedId}
                onSelectNode={setSelectedId}
                onSelectEdge={setSelectedId}
              />
            </>
          )}
        </div>

        <TraceControls
          playing={playing}
          onPlayPause={() => setPlaying((v) => !v)}
          speed={speed}
          onSpeed={setSpeed}
          progress={progress}
          onScrub={(v) => {
            setProgress(v);
            setPlaying(false);
          }}
          stepIndex={frame.stepIndex}
          stepCount={frame.stepCount}
          onStepBack={() => handleStep(-1)}
          onStepForward={() => handleStep(1)}
        />
      </div>

      {/* ── Right: one context panel — case summary, or the selected
          node/transfer's evidence when something is picked on the graph.
          This used to be two separate columns (Case Context on the left,
          a whole other "Intelligence Inspector" on the right) flanking the
          graph. One column, two modes, more room for the graph itself. */}
      <div className="ug-workspace__right" style={{ padding: 0, overflowY: "auto" }}>
        <div
          style={{
            padding: "0.75rem 1.25rem",
            borderBottom: "1px solid var(--border-strong)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <p className="ug-section-title" style={{ marginBottom: 0 }}>
            {selectedId ? "Evidence" : "Case Context"}
          </p>
          {selectedId && (
            <button
              onClick={() => setSelectedId(null)}
              style={{
                fontFamily: MONO,
                fontSize: "0.58rem",
                letterSpacing: "0.1em",
                background: "none",
                border: "none",
                color: "var(--color-accent)",
                cursor: "pointer",
                padding: 0,
              }}
            >
              ← Case
            </button>
          )}
        </div>

        {selectedId ? (
          <IntelligenceInspector
            selectedId={selectedId}
            nodes={nodes}
            edges={edgesForLayout}
            meta={meta}
            correlationSignal={correlationSignal}
            linkedComplaints={linkedComplaints}
            targetAddress={activeWallet}
            riskTier={riskTier}
          />
        ) : (
          <div style={{ padding: "1rem 1.25rem" }}>
            {[
              { k: "Case", v: activeCaseNumber ?? "No case" },
              { k: "Target", v: activeWallet, mono: true },
              { k: "Chain", v: chain },
              {
                k: "Status",
                v: traceLoading ? "Tracing" : (activeCaseStatus ?? "Active"),
              },
            ].map(({ k, v, mono }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span
                  className="ug-data-row__value"
                  style={{ fontFamily: mono ? MONO : undefined, fontSize: "0.74rem" }}
                >
                  {v}
                </span>
              </div>
            ))}

            <div className="ug-divider" />

            <button
              onClick={() => navigate({ to: "/dashboard/risk" })}
              className="ug-glance-chip"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.3rem",
                width: "100%",
                padding: "0.6rem 0.75rem",
                marginBottom: "0.5rem",
                background: "var(--bg-2)",
                border: "1px solid var(--border-strong)",
                borderRadius: 2,
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              <span
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  width: "100%",
                }}
              >
                <span style={{ fontFamily: MONO, fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
                  Risk
                </span>
                <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span
                    style={{
                      fontSize: "0.9rem",
                      fontWeight: 700,
                      color: riskTierColor(riskTier),
                    }}
                  >
                    {riskScore !== null
                      ? `${formatRiskScore(riskScore)}/100`
                      : riskError
                        ? "—"
                        : riskLoading
                          ? "…"
                          : "N/A"}
                  </span>
                  <span style={{ fontSize: "0.6rem", color: "var(--color-accent)" }}>View →</span>
                </span>
              </span>
              {/* The real reason the number is what it is, right where the
                  number is — a low score with nothing backing it visible is
                  indistinguishable from a broken one. This is the same
                  evidence the Risk Intelligence page shows in full, just
                  compressed to a one-line factor count so it doesn't need a
                  click to start being credible. */}
              {riskScore !== null && riskSignals.length > 0 && (
                <span style={{ fontFamily: MONO, fontSize: "0.56rem", color: "var(--color-muted-foreground)" }}>
                  {(() => {
                    const raising = riskSignals.filter((s) => s.direction === "increases_risk").length;
                    const lowering = riskSignals.length - raising;
                    if (raising === 0) {
                      return `${lowering} of ${lowering} factors lower risk — no risk-raising signal found`;
                    }
                    if (lowering === 0) {
                      return `${raising} of ${raising} factors raise risk`;
                    }
                    return `${raising} factor${raising === 1 ? "" : "s"} raise risk, ${lowering} lower it`;
                  })()}
                </span>
              )}
            </button>

            {/* The backend has no concept of "confidence" separate from the
                risk score itself — no such field exists in the risk
                pipeline. Showing an honest "Not available" here instead of
                a fabricated percentage (a decorative "92% confidence" used
                to appear elsewhere in this app with nothing computing it). */}
            <div className="ug-data-row">
              <span className="ug-data-row__key">Confidence</span>
              <span
                className="ug-data-row__value"
                style={{ fontSize: "0.68rem", color: "var(--color-muted-foreground)" }}
              >
                Not available
              </span>
            </div>

            <div className="ug-divider" />

            {/* Labeled "Key Signal" — it now opens the Network Signals page
                it's named after, not Cross-Victim. Cross-Victim is still one
                click away in the sidebar for the fuller complaints table. */}
            <button
              onClick={() => navigate({ to: "/dashboard/signals" })}
              className="ug-glance-chip"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                width: "100%",
                padding: "0.6rem 0.75rem",
                marginBottom: "0.5rem",
                background: "var(--bg-2)",
                border: "1px solid var(--border-strong)",
                borderRadius: 2,
                cursor: "pointer",
              }}
            >
              <span style={{ fontFamily: MONO, fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
                Key Signal
              </span>
              <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.9rem", fontWeight: 700, color: "var(--color-signal)" }}>
                  {evidence ? evidence.strength : correlationSignal ? correlationSignal.signalStrength : "…"}
                </span>
                <span style={{ fontSize: "0.6rem", color: "var(--color-accent)" }}>View →</span>
              </span>
            </button>

            {[
              { k: "Victims", v: correlationSignal ? String(correlationSignal.victims) : "—" },
              { k: "Complaints", v: correlationSignal ? String(correlationSignal.complaints) : "—" },
              { k: "Nearest VASP", v: vasp ?? "Not yet attributed" },
              { k: "Transfers", v: String(timeline.steps.length) },
            ].map(({ k, v }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span className="ug-data-row__value" style={{ fontSize: "0.74rem" }}>
                  {v}
                </span>
              </div>
            ))}

            <BackendOfflineBanner error={traceError} context="trace" />

            {meta && <TraceProvenance meta={meta} />}

            <div className="ug-divider" />

            <button
              onClick={() => navigate({ to: "/dashboard/evidence" })}
              style={{
                fontFamily: MONO,
                fontSize: "0.62rem",
                letterSpacing: "0.08em",
                color: "var(--color-accent)",
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 0,
                marginBottom: "0.75rem",
                display: "block",
              }}
            >
              Open Evidence Trail →
            </button>

            {/* Developer diagnostics: proves the rendered graph matches the
                trace dataset rather than asking anyone to take it on trust. */}
            {meta && (
              <>
                <div className="ug-divider" />
                <button
                  onClick={() => setShowDiagnostics((v) => !v)}
                  style={{
                    fontFamily: MONO,
                    fontSize: "0.56rem",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    background: "none",
                    border: "none",
                    color: "var(--color-muted-foreground)",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  {showDiagnostics ? "▾" : "▸"} Trace diagnostics
                </button>
                {showDiagnostics && (
                  <div style={{ marginTop: "0.5rem" }}>
                    {[
                      { k: "Engine nodes", v: String(meta.nodeCount) },
                      { k: "Graph nodes", v: String(rawNodes.length) },
                      { k: "Rendered nodes", v: String(frame.revealedNodes.size) },
                      { k: "Graph edges", v: String(edges.length) },
                      { k: "Timeline steps", v: String(timeline.steps.length) },
                      { k: "Rendered edges", v: String(frame.revealedEdges.size) },
                      { k: "Dropped edges", v: String(meta.orphanedEdges) },
                      { k: "Canvas", v: `${layout.width}×${layout.height}` },
                      { k: "Trace ID", v: meta.traceId.slice(0, 8) },
                      { k: "Hash", v: meta.reproducibleHash.slice(0, 10) },
                    ].map(({ k, v }) => (
                      <div key={k} className="ug-data-row">
                        <span className="ug-data-row__key">{k}</span>
                        <span className="ug-data-row__value" style={{ fontFamily: MONO, fontSize: "0.66rem" }}>
                          {v}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
