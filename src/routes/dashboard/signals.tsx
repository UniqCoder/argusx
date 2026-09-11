import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect, useRef } from "react";
import { MOCK_CASES } from "@/lib/mock-data";
import { useCorrelation } from "@/hooks/use-correlation";
import { useCaseContext } from "@/store/case-context-store";
import { WalletSelector } from "@/components/dashboard/WalletSelector";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import type { Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/signals")({
  component: NetworkSignals,
});

// ── Graph nodes / edges ───────────────────────────────────────────────────

const TX_NODES = [
  { id: "w1", x: 100, y: 140, label: "WALLET A", type: "reported" },
  { id: "w2", x: 245, y: 78, label: "WALLET B", type: "intermediate" },
  { id: "w3", x: 245, y: 202, label: "WALLET C", type: "intermediate" },
  { id: "w4", x: 385, y: 140, label: "BRIDGE", type: "bridge" },
  { id: "w5", x: 510, y: 140, label: "EXCHANGE", type: "exchange" },
];
const TX_EDGES = [
  { from: "w1", to: "w2" },
  { from: "w1", to: "w3" },
  { from: "w2", to: "w4" },
  { from: "w3", to: "w4" },
  { from: "w4", to: "w5" },
];

const CX_NODES = [
  { id: "c1", x: 300, y: 32, label: "VICTIM A", type: "victim" },
  { id: "c2", x: 480, y: 32, label: "VICTIM B", type: "victim" },
  { id: "c3", x: 120, y: 32, label: "VICTIM C", type: "victim" },
  { id: "c4", x: 120, y: 130, label: "COMPLAINT", type: "complaint" },
  { id: "c5", x: 300, y: 130, label: "COMPLAINT", type: "complaint" },
  { id: "c6", x: 480, y: 130, label: "COMPLAINT", type: "complaint" },
  { id: "c7", x: 300, y: 230, label: "REPORTED", type: "reported" },
  { id: "c8", x: 300, y: 316, label: "RELATED", type: "intermediate" },
];
const CX_EDGES = [
  { from: "c1", to: "c5" },
  { from: "c2", to: "c6" },
  { from: "c3", to: "c4" },
  { from: "c4", to: "c7" },
  { from: "c5", to: "c7" },
  { from: "c6", to: "c7" },
  { from: "c7", to: "c8" },
];

const NODE_C: Record<string, string> = {
  victim: "oklch(0.72 0.024 250)",
  complaint: "oklch(0.79 0.15 74)",
  reported: "oklch(0.64 0.22 18)",
  intermediate: "oklch(0.83 0.14 205)",
  bridge: "oklch(0.79 0.15 74)",
  exchange: "oklch(0.79 0.15 74)",
};

function NetworkGraph({
  nodes,
  edges,
  viewBox,
}: {
  nodes: typeof TX_NODES;
  edges: typeof TX_EDGES;
  viewBox: string;
}) {
  const particlesRef = useRef<{ id: number; ei: number; t: number }[]>([]);
  const animRef = useRef<number | undefined>(undefined);
  const lastRef = useRef<number>(0);
  const [, tick] = useState<number>(0);

  useEffect(() => {
    const frame = (now: number) => {
      const dt = now - lastRef.current;
      lastRef.current = now;
      particlesRef.current = particlesRef.current
        .map((p) => ({ ...p, t: p.t + dt / 850 }))
        .filter((p) => p.t < 1);
      if (Math.random() < 0.022 && edges.length) {
        particlesRef.current.push({
          id: now + Math.random(),
          ei: Math.floor(Math.random() * edges.length),
          t: 0,
        });
      }
      tick((n) => n + 1);
      animRef.current = requestAnimationFrame(frame);
    };
    animRef.current = requestAnimationFrame(frame);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, [edges.length]);

  const getN = (id: string) => nodes.find((n) => n.id === id)!;

  return (
    <svg viewBox={viewBox} style={{ width: "100%", height: "100%" }}>
      {[60, 120, 180, 240, 300].map((y) => (
        <line
          key={y}
          x1={0}
          y1={y}
          x2={620}
          y2={y}
          stroke="oklch(0.98 0 0 / 3%)"
          strokeWidth={1}
        />
      ))}
      {edges.map((e, i) => {
        const a = getN(e.from),
          b = getN(e.to);
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="oklch(0.83 0.14 205 / 24%)"
            strokeWidth={1}
          />
        );
      })}
      {particlesRef.current.map((p) => {
        const e = edges[p.ei];
        if (!e) return null;
        const a = getN(e.from),
          b = getN(e.to);
        return (
          <circle
            key={p.id}
            cx={a.x + (b.x - a.x) * p.t}
            cy={a.y + (b.y - a.y) * p.t}
            r={2.5}
            fill="oklch(0.83 0.14 205)"
            opacity={Math.min(1, 1 - Math.abs(p.t - 0.5) * 1.8 + 0.2)}
            style={{
              filter: "drop-shadow(0 0 3px oklch(0.83 0.14 205 / 70%))",
            }}
          />
        );
      })}
      {nodes.map((n) => {
        const col = NODE_C[n.type] ?? "var(--color-muted-foreground)";
        return (
          <g key={n.id}>
            <rect
              x={n.x - 10}
              y={n.y - 10}
              width={20}
              height={20}
              transform={`rotate(45, ${n.x}, ${n.y})`}
              fill={`${col.slice(0, -1)} / 10%)`}
              stroke={col}
              strokeWidth={1.5}
            />
            <text
              x={n.x}
              y={n.y + 26}
              textAnchor="middle"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 7.5,
                fill: "var(--color-muted-foreground)",
                letterSpacing: "0.08em",
              }}
            >
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────

function NetworkSignals() {
  const [view, setView] = useState<"tx" | "complaint">("tx");
  const navigate = useNavigate();
  const { activeWallet, activeChain, setActiveWallet } = useCaseContext();
  const chainToUse = (activeChain || "ETH") as Chain;

  const {
    signal: sig,
    linkedComplaints,
    loading,
    error,
  } = useCorrelation(activeWallet, chainToUse);

  const daysActive = (() => {
    if (linkedComplaints.length === 0) return 0;
    const earliest = Math.min(
      ...linkedComplaints.map((c) => new Date(c.filed_at).getTime()),
    );
    return Math.max(0, Math.round((Date.now() - earliest) / 86_400_000));
  })();

  return (
    <>
      {/* Page header — badge sits inline at end, aligned to bottom */}
      <div className="ug-page-header" style={{ alignItems: "flex-end" }}>
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Intelligence</p>
          <h1 className="ug-page-header__title">Network Signals</h1>
          <p className="ug-page-header__sub">
            {activeWallet
              ? `Correlating: ${activeWallet.slice(0, 12)}...`
              : "Cross-victim correlation — same blockchain infrastructure, multiple independent fraud complaints."}
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            flexShrink: 0,
            marginBottom: "0.25rem",
          }}
        >
          <WalletSelector />
          {sig && (
            <span
              className="ug-badge ug-badge--critical"
              style={{ fontSize: "0.6rem", padding: "0.28rem 0.65rem" }}
            >
              Signal: {sig.signalStrength}
            </span>
          )}
        </div>
      </div>

      {!activeWallet && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "1rem" }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
            No wallet selected yet — trace a wallet or pick one from the selector above.
          </p>
        </div>
      )}

      {activeWallet && !sig && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "1rem" }}>
          {loading && !error && (
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
              Correlating…
            </p>
          )}
          <BackendOfflineBanner error={error} context="network signal" />
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 300px",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        {/* Left column */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Signal detection banner */}
          {sig && (
          <div className="ug-surface ug-surface--critical">
            <div className="ug-panel-header">
              <div>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.54rem",
                    letterSpacing: "0.3em",
                    textTransform: "uppercase",
                    color: "var(--color-signal)",
                    marginBottom: "0.3rem",
                  }}
                >
                  NETWORK SIGNAL DETECTED
                </p>
                <h2
                  style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    letterSpacing: "-0.02em",
                    color: "var(--color-foreground)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {sig.wallet}
                </h2>
              </div>
              <button
                className="ug-btn-primary"
                onClick={() => {
                  if (activeWallet) setActiveWallet(activeWallet, chainToUse);
                  navigate({ to: "/dashboard/investigation" });
                }}
                style={{
                  padding: "0.45rem 1rem",
                  fontSize: "0.66rem",
                  flexShrink: 0,
                }}
              >
                Open Investigation
              </button>
            </div>

            {/* Stats grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                borderTop: "1px solid var(--border-strong)",
              }}
            >
              {[
                {
                  label: "Independent Victims",
                  value: sig.victims,
                  color: "var(--color-signal)",
                },
                {
                  label: "Related Complaints",
                  value: sig.complaints,
                  color: "var(--color-primary)",
                },
                {
                  label: "States Affected",
                  value: sig.states,
                  color: "var(--color-accent)",
                },
                {
                  label: "Days Active",
                  value: daysActive,
                  color: "var(--color-foreground)",
                },
              ].map((s, i) => (
                <div
                  key={s.label}
                  style={{
                    padding: "1rem 1.1rem",
                    background: "var(--bg-2)",
                    borderRight:
                      i < 3 ? "1px solid var(--border-strong)" : "none",
                    borderTop: `2px solid ${s.color}`,
                  }}
                >
                  <p
                    style={{
                      fontSize: "1.85rem",
                      fontWeight: 700,
                      letterSpacing: "-0.05em",
                      color: s.color,
                      lineHeight: 1,
                    }}
                  >
                    {s.value}
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.54rem",
                      letterSpacing: "0.16em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                      marginTop: "0.3rem",
                    }}
                  >
                    {s.label}
                  </p>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div
              style={{
                padding: "0.75rem 1.25rem",
                borderTop: "1px solid var(--border-strong)",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.62rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                Funds at risk:
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  color: "var(--color-primary)",
                }}
              >
                {sig.totalFundsAtRisk}
              </span>
            </div>
          </div>
          )}

          {/* Graph panel */}
          <div className="ug-surface">
            <div className="ug-panel-header">
              <div className="ug-pills" style={{ margin: 0 }}>
                {(["tx", "complaint"] as const).map((v) => (
                  <button
                    key={v}
                    className={`ug-pill${view === v ? " is-active" : ""}`}
                    onClick={() => setView(v)}
                  >
                    {v === "tx" ? "Transaction Network" : "Complaint Network"}
                  </button>
                ))}
              </div>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.54rem",
                  color: "var(--color-muted-foreground)",
                  letterSpacing: "0.1em",
                  flexShrink: 0,
                }}
              >
                LIVE
              </span>
            </div>
            <div style={{ padding: "1.25rem", height: 280 }}>
              {view === "tx" ? (
                <NetworkGraph
                  nodes={TX_NODES}
                  edges={TX_EDGES}
                  viewBox="0 0 620 260"
                />
              ) : (
                <NetworkGraph
                  nodes={CX_NODES}
                  edges={CX_EDGES}
                  viewBox="0 0 620 360"
                />
              )}
            </div>
          </div>
        </div>

        {/* Right: linked cases */}
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Linked Cases
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.56rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              {MOCK_CASES.slice(0, 4).length} linked
            </span>
          </div>
          {MOCK_CASES.slice(0, 4).map((c) => {
            const railColor =
              c.networkSignal === "HIGH"
                ? "var(--color-signal)"
                : c.networkSignal === "MEDIUM"
                  ? "var(--color-primary)"
                  : "var(--color-accent)";
            return (
              <div
                key={c.id}
                className="ug-event"
                onClick={() => navigate({ to: "/dashboard/investigation" })}
              >
                <div
                  className="ug-event__bar"
                  style={{ background: railColor }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.6rem",
                        letterSpacing: "0.1em",
                        color: "var(--color-accent)",
                      }}
                    >
                      {c.id}
                    </span>
                    <span
                      className={`ug-badge ug-badge--${c.networkSignal.toLowerCase()}`}
                    >
                      {c.networkSignal}
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: "0.76rem",
                      fontWeight: 600,
                      color: "var(--color-foreground)",
                      marginBottom: "0.2rem",
                    }}
                  >
                    {c.fraudType}
                  </p>
                  <div style={{ display: "flex", gap: "0.75rem" }}>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.58rem",
                        color: "var(--color-muted-foreground)",
                      }}
                    >
                      {c.blockchain}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.58rem",
                        color: "var(--color-muted-foreground)",
                      }}
                    >
                      {c.victimCount} victims
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
}
