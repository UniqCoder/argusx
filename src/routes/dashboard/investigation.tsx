import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useRef, useCallback } from "react";
import { type TraceNode, type TraceEdge } from "@/lib/mock-data";
import { useCaseContext } from "@/store/case-context-store";
import { useWalletTrace, useWalletRisk } from "@/hooks/use-wallet";
import { useCorrelation } from "@/hooks/use-correlation";
import { useForceLayout } from "@/hooks/use-force-layout";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import type { Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/investigation")({
  component: InvestigationWorkspace,
});

// ─── Colour helpers ───────────────────────────────────────────────────────────
const NODE_COLOR: Record<TraceNode["type"], string> = {
  victim: "oklch(0.72 0.024 250)",
  reported: "oklch(0.64 0.22 18)",
  intermediate: "oklch(0.83 0.14 205)",
  bridge: "oklch(0.79 0.15 74)",
  mixer: "oklch(0.64 0.22 18 / 70%)",
  exchange: "oklch(0.79 0.15 74)",
};

// ─── Trace Graph ─────────────────────────────────────────────────────────────
interface TraceGraphProps {
  nodes: TraceNode[];
  edges: TraceEdge[];
  selectedId: string | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}

function TraceGraph({
  nodes,
  edges,
  selectedId,
  onSelectNode,
  onSelectEdge,
}: TraceGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null);

  const getNode = useCallback(
    (id: string) => nodes.find((n) => n.id === id),
    [nodes],
  );

  return (
    <svg
      ref={svgRef}
      viewBox="0 0 980 420"
      style={{ width: "100%", height: "100%", overflow: "visible" }}
    >
      <defs>
        <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feComposite in="SourceGraphic" in2="blur" operator="over" />
        </filter>
        <marker
          id="arrow"
          markerWidth="6"
          markerHeight="6"
          refX="5"
          refY="3"
          orient="auto"
        >
          <path d="M0 0 L6 3 L0 6 z" fill="oklch(0.83 0.14 205 / 40%)" />
        </marker>
      </defs>

      {/* Edges — unresolved (not yet reached in the real chronological
          replay order) render dashed/faint; becoming resolved fades the
          edge in for real, tied to the real reveal step, not a fake loop. */}
      {edges.map((edge) => {
        const a = getNode(edge.from);
        const b = getNode(edge.to);
        if (!a || !b) return null;
        const isSelected = selectedId === edge.id;
        return (
          <line
            key={edge.id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke={
              !edge.resolved
                ? "oklch(0.72 0.024 250 / 20%)"
                : isSelected
                  ? "var(--color-accent)"
                  : "oklch(0.83 0.14 205 / 35%)"
            }
            strokeWidth={isSelected ? 2 : 1.5}
            strokeDasharray={edge.resolved ? "none" : "5 4"}
            markerEnd={edge.resolved ? "url(#arrow)" : undefined}
            style={{
              cursor: "pointer",
              opacity: edge.resolved ? 1 : 0.5,
              transition: "opacity 0.5s ease, stroke 0.3s ease",
            }}
            onClick={() => onSelectEdge(edge.id)}
          />
        );
      })}

      {/* Nodes */}
      {nodes.map((node) => {
        const color = NODE_COLOR[node.type];
        const isSelected = selectedId === node.id;
        const isUnresolved = !node.resolved;
        return (
          <g
            key={node.id}
            className="ug-node"
            style={{
              cursor: "pointer",
              opacity: isUnresolved ? 0.35 : 1,
              transform: `translate(${node.x}px, ${node.y}px) scale(${isUnresolved ? 0.7 : 1})`,
              transformOrigin: `${node.x}px ${node.y}px`,
              transition: "opacity 0.4s ease, transform 0.4s cubic-bezier(0.22, 1, 0.36, 1)",
            }}
            onClick={() => onSelectNode(node.id)}
          >
            {/* Outer ring for selected */}
            {isSelected && (
              <circle
                cx={0}
                cy={0}
                r={26}
                fill="none"
                stroke="var(--color-accent)"
                strokeWidth={1.5}
                opacity={0.5}
                style={{ animation: "none" }}
              />
            )}
            {/* Main node */}
            <circle
              cx={0}
              cy={0}
              r={18}
              fill={color.replace(")", " / 12%)")}
              stroke={color}
              strokeWidth={1.5}
              filter={isSelected ? "url(#glow-cyan)" : undefined}
            />
            {/* Node icon initial */}
            <text
              x={0}
              y={5}
              textAnchor="middle"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                fontWeight: 600,
                fill: color,
                pointerEvents: "none",
              }}
            >
              {node.type[0]?.toUpperCase()}
            </text>
            {/* Label below */}
            <text
              x={0}
              y={34}
              textAnchor="middle"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 8,
                fill: "var(--color-muted-foreground)",
                letterSpacing: "0.08em",
                pointerEvents: "none",
              }}
            >
              {node.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ─── Trace Controls ───────────────────────────────────────────────────────────
function TraceControls({
  playing,
  onPlayPause,
  speed,
  onSpeed,
  progress,
  onScrub,
  totalNodes,
}: {
  playing: boolean;
  onPlayPause: () => void;
  speed: number;
  onSpeed: (s: number) => void;
  progress: number;
  onScrub: (v: number) => void;
  totalNodes: number;
}) {
  return (
    <div className="ug-trace-controls">
      {/* Replay */}
      <button
        className="ug-btn-ghost"
        onClick={() => onScrub(0)}
        style={{
          padding: "0.3rem 0.75rem",
          fontSize: "0.68rem",
          borderRadius: "2px",
        }}
      >
        ↺ Replay
      </button>

      {/* Play/Pause */}
      <button
        className="ug-btn-ghost"
        onClick={onPlayPause}
        style={{
          padding: "0.3rem 0.9rem",
          fontSize: "0.68rem",
          borderRadius: "2px",
        }}
      >
        {playing ? "⏸ Pause" : "▶ Play"}
      </button>

      {/* Speed selector */}
      <div style={{ display: "flex", gap: "2px" }}>
        {[1, 2, 4].map((s) => (
          <button
            key={s}
            onClick={() => onSpeed(s)}
            style={{
              padding: "0.25rem 0.6rem",
              borderRadius: "2px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              background:
                speed === s ? "oklch(0.83 0.14 205 / 16%)" : "transparent",
              border:
                speed === s
                  ? "1px solid oklch(0.83 0.14 205 / 40%)"
                  : "1px solid var(--border-strong)",
              color:
                speed === s
                  ? "var(--color-accent)"
                  : "var(--color-muted-foreground)",
              cursor: "pointer",
              transition: "all 0.15s",
            }}
          >
            {s}×
          </button>
        ))}
      </div>

      {/* Timeline scrubber */}
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          gap: "0.75rem",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            color: "var(--color-muted-foreground)",
            whiteSpace: "nowrap",
          }}
        >
          Hop {Math.ceil(progress * totalNodes)} /{" "}
          {totalNodes}
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.01}
          value={progress}
          onChange={(e) => onScrub(parseFloat(e.target.value))}
          style={{
            flex: 1,
            accentColor: "var(--color-accent)",
            height: 3,
            cursor: "pointer",
          }}
        />
      </div>
    </div>
  );
}

// ─── Intelligence Inspector ───────────────────────────────────────────────────
function IntelligenceInspector({
  selectedId,
  nodes,
  edges,
}: {
  selectedId: string | null;
  nodes: TraceNode[];
  edges: TraceEdge[];
}) {
  const node = nodes.find((n) => n.id === selectedId);
  const edge = edges.find((e) => e.id === selectedId);

  if (!selectedId) {
    return (
      <div style={{ padding: "1.25rem", textAlign: "center" }}>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            letterSpacing: "0.2em",
            textTransform: "uppercase",
            color: "var(--color-muted-foreground)",
            marginBottom: "0.5rem",
          }}
        >
          Intelligence Inspector
        </p>
        <p
          style={{
            fontSize: "0.78rem",
            color: "var(--color-muted-foreground)",
            lineHeight: 1.6,
          }}
        >
          Select a wallet node or connection edge to inspect evidence.
        </p>
      </div>
    );
  }

  if (node) {
    const color = NODE_COLOR[node.type];
    return (
      <div style={{ padding: "1.25rem" }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.6rem",
            marginBottom: "1rem",
          }}
        >
          <div
            style={{
              width: 10,
              height: 10,
              borderRadius: "999px",
              background: color,
            }}
          />
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              letterSpacing: "0.22em",
              textTransform: "uppercase",
              color,
            }}
          >
            {node.type}
          </p>
        </div>
        <h3
          style={{
            fontSize: "0.92rem",
            fontWeight: 700,
            color: "var(--color-foreground)",
            marginBottom: "1rem",
            letterSpacing: "-0.02em",
          }}
        >
          {node.label}
        </h3>

        <div>
          {[
            { k: "Address", v: node.address },
            { k: "Blockchain", v: node.blockchain },
            { k: "Amount", v: node.amount ?? "—" },
            { k: "Status", v: node.resolved ? "Resolved" : "Unresolved" },
          ].map(({ k, v }) => (
            <div key={k} className="ug-data-row">
              <span className="ug-data-row__key">{k}</span>
              <span
                className="ug-data-row__value"
                style={{
                  fontFamily: k === "Address" ? "var(--font-mono)" : undefined,
                }}
              >
                {v}
              </span>
            </div>
          ))}
        </div>

        <div className="ug-divider" />

        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            color: "var(--color-muted-foreground)",
            lineHeight: 1.6,
          }}
        >
          Per-wallet risk scoring lives on the dedicated Risk Intelligence
          page — this trace endpoint doesn't compute a score per hop.
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
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            letterSpacing: "0.22em",
            textTransform: "uppercase",
            color: "var(--color-accent)",
            marginBottom: "1rem",
          }}
        >
          Connection Evidence
        </p>

        <div>
          {[
            { k: "From", v: fromNode?.label ?? edge.from },
            { k: "To", v: toNode?.label ?? edge.to },
            { k: "Method", v: edge.method },
            { k: "Amount", v: edge.amount },
            { k: "Data Source", v: edge.dataSource },
            { k: "Timestamp", v: edge.timestamp || "Unresolved" },
          ].map(({ k, v }) => (
            <div key={k} className="ug-data-row">
              <span className="ug-data-row__key">{k}</span>
              <span className="ug-data-row__value">{v}</span>
            </div>
          ))}
        </div>

        {edge.txHash && (
          <>
            <div className="ug-divider" />
            <p className="ug-section-title">Transaction Hash</p>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-accent)",
                wordBreak: "break-all",
                lineHeight: 1.5,
              }}
            >
              {edge.txHash}
            </p>
          </>
        )}

        <div
          style={{
            marginTop: "1rem",
            padding: "0.75rem",
            background: edge.resolved
              ? "oklch(0.83 0.14 205 / 6%)"
              : "oklch(0.64 0.22 18 / 6%)",
            border: `1px solid ${edge.resolved ? "oklch(0.83 0.14 205 / 20%)" : "oklch(0.64 0.22 18 / 20%)"}`,
            borderRadius: "2px",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.65rem",
              color: edge.resolved
                ? "var(--color-accent)"
                : "var(--color-signal)",
              letterSpacing: "0.1em",
            }}
          >
            {edge.resolved
              ? "✓ Resolved connection"
              : "⚠ Unresolved — awaiting on-chain confirmation"}
          </p>
        </div>
      </div>
    );
  }

  return null;
}

// ─── Investigation Workspace ──────────────────────────────────────────────────
function InvestigationWorkspace() {
  const navigate = useNavigate();
  const { activeWallet, activeChain } = useCaseContext();
  const chain = (activeChain || "ETH") as Chain;

  const {
    nodes: rawNodes,
    edges,
    vasp,
    loading: traceLoading,
    error: traceError,
  } = useWalletTrace(activeWallet, chain);
  const nodes = useForceLayout(rawNodes, edges);

  const { riskScore, error: riskError } = useWalletRisk(activeWallet, chain);

  const { signal: correlationSignal } = useCorrelation(activeWallet, chain);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);
  const [progress, setProgress] = useState(1);

  // Reset the playback scrubber to the start of a fresh trace result.
  useEffect(() => {
    setProgress(nodes.length > 1 ? 0 : 1);
    setSelectedId(null);
  }, [activeWallet, chain]);

  // Progress auto-advance when playing
  useEffect(() => {
    if (!playing) return;
    const interval = setInterval(() => {
      setProgress((p) => {
        if (p >= 1) {
          setPlaying(false);
          return 1;
        }
        return Math.min(1, p + 0.003 * speed);
      });
    }, 50);
    return () => clearInterval(interval);
  }, [playing, speed]);

  // Reveal order follows the real on-chain time each node was reached
  // (firstTaintedAt) — the root/searched wallet has none and always goes
  // first. This makes Play/Replay an honest chronological reconstruction
  // of when the money actually moved, not an arbitrary array-order reveal.
  const revealOrder = [...nodes].sort((a, b) => {
    if (!a.firstTaintedAt && !b.firstTaintedAt) return 0;
    if (!a.firstTaintedAt) return -1;
    if (!b.firstTaintedAt) return 1;
    return (
      new Date(a.firstTaintedAt).getTime() -
      new Date(b.firstTaintedAt).getTime()
    );
  });
  const revealedCount = Math.max(1, Math.ceil(progress * nodes.length));
  const revealedIds = new Set(
    revealOrder.slice(0, revealedCount).map((n) => n.id),
  );
  const visibleNodes = nodes.map((n) => ({
    ...n,
    resolved: n.resolved && revealedIds.has(n.id),
  }));
  const visibleEdges = edges.map((e) => ({
    ...e,
    resolved: e.resolved && revealedIds.has(e.from) && revealedIds.has(e.to),
  }));

  if (!activeWallet) {
    return (
      <div className="ug-surface" style={{ padding: "1.5rem" }}>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.68rem",
            color: "var(--color-muted-foreground)",
          }}
        >
          No wallet selected — go to Trace Wallet and paste an address to
          start an investigation.
        </p>
      </div>
    );
  }

  return (
    <div
      className="ug-workspace"
      style={{ margin: "-2rem -2.25rem", height: "calc(100vh - 48px)" }}
    >
      {/* ── Left: Case Context ── */}
      <div className="ug-workspace__left">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "1rem",
          }}
        >
          <p className="ug-section-title">Case Context</p>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.6rem",
              color: "var(--color-accent)",
              opacity: 0.8,
            }}
          >
            Active
          </span>
        </div>

        <div style={{ marginBottom: "1rem" }}>
          {[
            { k: "Wallet", v: activeWallet },
            { k: "Chain", v: chain },
            { k: "Nearest VASP", v: vasp ?? "Not yet attributed" },
            { k: "Hops Found", v: String(edges.length) },
          ].map(({ k, v }) => (
            <div key={k} className="ug-data-row">
              <span className="ug-data-row__key">{k}</span>
              <span
                className="ug-data-row__value"
                style={{
                  fontFamily: k === "Wallet" ? "var(--font-mono)" : undefined,
                  fontSize: "0.74rem",
                }}
              >
                {v}
              </span>
            </div>
          ))}
        </div>

        <BackendOfflineBanner error={traceError} context="trace" />

        <div className="ug-divider" />

        {/* Risk + Network Signal — compact glance only; full detail lives on
            their own dedicated pages (Risk Intelligence / Cross-Victim), not
            duplicated here. */}
        <button
          onClick={() => navigate({ to: "/dashboard/risk" })}
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
            borderRadius: "2px",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            Risk Score
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span
              style={{
                fontSize: "0.9rem",
                fontWeight: 700,
                color: "var(--color-signal)",
              }}
            >
              {riskScore !== null ? `${riskScore}/100` : riskError ? "—" : "…"}
            </span>
            <span style={{ fontSize: "0.6rem", color: "var(--color-accent)" }}>
              View →
            </span>
          </span>
        </button>

        <button
          onClick={() => navigate({ to: "/dashboard/cross-victim" })}
          className="ug-glance-chip"
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            width: "100%",
            padding: "0.6rem 0.75rem",
            background: "var(--bg-2)",
            border: "1px solid var(--border-strong)",
            borderRadius: "2px",
            cursor: "pointer",
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            Network Signal
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <span
              style={{
                fontSize: "0.9rem",
                fontWeight: 700,
                color: "var(--color-signal)",
              }}
            >
              {correlationSignal ? correlationSignal.signalStrength : "…"}
            </span>
            <span style={{ fontSize: "0.6rem", color: "var(--color-accent)" }}>
              View →
            </span>
          </span>
        </button>
      </div>

      {/* ── Center: Live Money Trail ── */}
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
            Live Money Trail
          </p>
          <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
            <span className="ug-system-live__dot" />
            {playing ? "TRACING" : "PAUSED"}
          </div>
        </div>

        <div className="ug-trace-canvas">
          {nodes.length === 0 ? (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-muted-foreground)",
                textAlign: "center",
                marginTop: "2rem",
              }}
            >
              {traceLoading
                ? "Tracing…"
                : traceError
                  ? "Trace failed — see the error on the left."
                  : "No trace data for this wallet yet."}
            </p>
          ) : (
            <TraceGraph
              nodes={visibleNodes}
              edges={visibleEdges}
              selectedId={selectedId}
              onSelectNode={setSelectedId}
              onSelectEdge={setSelectedId}
            />
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
          totalNodes={nodes.length}
        />
      </div>

      {/* ── Right: Intelligence Inspector ── */}
      <div className="ug-workspace__right" style={{ padding: 0 }}>
        <div
          style={{
            padding: "0.75rem 1.25rem",
            borderBottom: "1px solid var(--border-strong)",
          }}
        >
          <p className="ug-section-title" style={{ marginBottom: 0 }}>
            Intelligence Inspector
          </p>
        </div>
        <IntelligenceInspector
          selectedId={selectedId}
          nodes={visibleNodes}
          edges={visibleEdges}
        />
      </div>
    </div>
  );
}
