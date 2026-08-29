import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { COMMAND_CENTER_STATS } from "@/lib/mock-data";
import type { IntelEvent } from "@/lib/mock-data";
import { useAlerts } from "@/hooks/use-alerts";
import { useCases } from "@/hooks/use-cases";

export const Route = createFileRoute("/dashboard/")({
  component: CommandCenter,
});

// -- Live Intelligence Map -------------------------------------------------

const MAP_NODES = [
  { id: "v1", label: "VICTIM", x: 80, y: 140, type: "victim" },
  { id: "r1", label: "REPORTED", x: 220, y: 100, type: "reported" },
  { id: "i1", label: "INTERMEDIATE", x: 360, y: 72, type: "intermediate" },
  { id: "i2", label: "INTERMEDIATE", x: 360, y: 200, type: "intermediate" },
  { id: "b1", label: "BRIDGE", x: 490, y: 136, type: "bridge" },
  { id: "e1", label: "EXCHANGE", x: 620, y: 136, type: "exchange" },
];

const MAP_EDGES = [
  { id: "e1", from: "v1", to: "r1" },
  { id: "e2", from: "r1", to: "i1" },
  { id: "e3", from: "r1", to: "i2" },
  { id: "e4", from: "i1", to: "b1" },
  { id: "e5", from: "i2", to: "b1" },
  { id: "e6", from: "b1", to: "e1" },
];

const NODE_COLORS: Record<string, string> = {
  victim: "oklch(0.72 0.024 250)",
  reported: "oklch(0.64 0.22 18)",
  intermediate: "oklch(0.83 0.14 205)",
  bridge: "oklch(0.79 0.15 74)",
  exchange: "oklch(0.79 0.15 74)",
};

function getNode(id: string) {
  return MAP_NODES.find((n) => n.id === id)!;
}

function LiveIntelligenceMap() {
  const [particles, setParticles] = useState<
    { id: number; edgeIdx: number; t: number }[]
  >([]);
  const tickRef = useRef<number>(0);
  const animRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    let last = 0;
    const tick = (now: number) => {
      const dt = now - last;
      last = now;
      tickRef.current += dt;
      if (tickRef.current > 1100) {
        tickRef.current = 0;
        const edgeIdx = Math.floor(Math.random() * MAP_EDGES.length);
        setParticles((p) => [...p.slice(-14), { id: now, edgeIdx, t: 0 }]);
      }
      setParticles((p) =>
        p.map((x) => ({ ...x, t: x.t + dt / 850 })).filter((x) => x.t < 1.05),
      );
      animRef.current = requestAnimationFrame(tick);
    };
    animRef.current = requestAnimationFrame(tick);
    return () => {
      if (animRef.current) cancelAnimationFrame(animRef.current);
    };
  }, []);

  return (
    <svg
      viewBox="0 0 720 280"
      className="ug-map"
      style={{ width: "100%", height: "100%" }}
    >
      {/* Grid lines — subtle structure */}
      {[70, 140, 210].map((y) => (
        <line
          key={y}
          x1={0}
          y1={y}
          x2={720}
          y2={y}
          stroke="oklch(0.98 0 0 / 3%)"
          strokeWidth={1}
        />
      ))}

      {/* Edges */}
      {MAP_EDGES.map((edge) => {
        const a = getNode(edge.from),
          b = getNode(edge.to);
        return (
          <line
            key={edge.id}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            className="ug-map__edge"
          />
        );
      })}

      {/* Particles */}
      {particles.map((p) => {
        const edge = MAP_EDGES[p.edgeIdx]!;
        const a = getNode(edge.from),
          b = getNode(edge.to);
        const t = Math.min(p.t, 1);
        return (
          <circle
            key={p.id}
            cx={a.x + (b.x - a.x) * t}
            cy={a.y + (b.y - a.y) * t}
            r={2.5}
            className="ug-map__particle"
            style={{ opacity: Math.min(1, 1 - Math.abs(p.t - 0.5) * 2 + 0.3) }}
          />
        );
      })}

      {/* Nodes — square diamonds */}
      {MAP_NODES.map((node) => {
        const color = NODE_COLORS[node.type] ?? "var(--color-muted-foreground)";
        return (
          <g key={node.id}>
            {/* Square rotated 45° = diamond */}
            <rect
              x={node.x - 11}
              y={node.y - 11}
              width={22}
              height={22}
              transform={`rotate(45, ${node.x}, ${node.y})`}
              fill={`${color.slice(0, -1)} / 10%)`}
              stroke={color}
              strokeWidth={1.5}
            />
            <text
              x={node.x}
              y={node.y + 28}
              textAnchor="middle"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 7.5,
                fill: "var(--color-muted-foreground)",
                letterSpacing: "0.1em",
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

// -- Severity helpers -----------------------------------------------------

function sevColor(s: IntelEvent["severity"]) {
  if (s === "CRITICAL") return "var(--color-signal)";
  if (s === "HIGH") return "var(--color-primary)";
  if (s === "MEDIUM") return "var(--color-accent)";
  return "var(--color-muted-foreground)";
}

const STAT_ACCENT: Record<number, string> = {
  0: "var(--color-foreground)",
  1: "var(--color-accent)",
  2: "var(--color-primary)",
  3: "var(--color-signal)",
};

// -- Command Center --------------------------------------------------------

function CommandCenter() {
  const navigate = useNavigate();
  const { events } = useAlerts();
  const { allCases } = useCases();
  const criticalCount = allCases.filter(
    (c) => c.traceStatus === "critical",
  ).length;

  const stats = [
    {
      label: "Active Cases",
      value:
        allCases.filter((c) => c.traceStatus !== "closed").length ||
        COMMAND_CENTER_STATS.activeCases,
    },
    {
      label: "Live Traces",
      value:
        allCases.filter((c) => c.traceStatus === "live-trace").length ||
        COMMAND_CENTER_STATS.liveTraces,
    },
    {
      label: "Network Signals",
      value:
        allCases.filter((c) => c.networkSignal !== "NONE").length ||
        COMMAND_CENTER_STATS.networkSignals,
    },
    {
      label: "Critical Alerts",
      value: criticalCount || COMMAND_CENTER_STATS.criticalAlerts,
    },
  ];

  return (
    <>
      {/* Page header */}
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Overview</p>
          <h1 className="ug-page-header__title">Command Center</h1>
          <p className="ug-page-header__sub">
            Real-time intelligence across active fraud investigations.
          </p>
        </div>
        <div className="ug-system-live">
          <span className="ug-system-live__dot" />
          System Live
        </div>
      </div>

      {/* Stat strip */}
      <div className="ug-stat-strip">
        {stats.map((s, i) => (
          <div
            key={s.label}
            className="ug-stat-cell"
            style={{ borderTop: `2px solid ${STAT_ACCENT[i]}` }}
          >
            <span
              className="ug-stat-cell__value"
              style={{ color: STAT_ACCENT[i] }}
            >
              {s.value}
            </span>
            <span className="ug-stat-cell__label">{s.label}</span>
          </div>
        ))}
      </div>

      {/* Two-column: map + feed */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        {/* Live Intelligence Map */}
        <div className="ug-surface">
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Live Intelligence Map
            </span>
            <div className="ug-system-live" style={{ fontSize: "0.56rem" }}>
              <span className="ug-system-live__dot" />
              LIVE
            </div>
          </div>
          <div style={{ padding: "1.25rem 1.25rem 1rem" }}>
            <div style={{ height: 240 }}>
              <LiveIntelligenceMap />
            </div>
            {/* Legend */}
            <div
              style={{
                display: "flex",
                gap: "1.25rem",
                marginTop: "1rem",
                flexWrap: "wrap",
                borderTop: "1px solid var(--border-subtle)",
                paddingTop: "0.75rem",
              }}
            >
              {Object.entries(NODE_COLORS).map(([type, color]) => (
                <div
                  key={type}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                  }}
                >
                  <div
                    style={{
                      width: 6,
                      height: 6,
                      background: color,
                      transform: "rotate(45deg)",
                    }}
                  />
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.56rem",
                      letterSpacing: "0.14em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Intel Feed */}
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Intel Feed
            </span>
            <div className="ug-system-live" style={{ fontSize: "0.56rem" }}>
              <span className="ug-system-live__dot" />
              LIVE
            </div>
          </div>
          {events.map((evt) => {
            const color = sevColor(evt.severity);
            return (
              <div
                key={evt.id}
                className="ug-event"
                onClick={() => navigate({ to: "/dashboard/alerts" })}
              >
                <div className="ug-event__bar" style={{ background: color }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      marginBottom: "0.2rem",
                    }}
                  >
                    <span className="ug-event__type" style={{ color }}>
                      {evt.type}
                    </span>
                    {!evt.read && (
                      <div
                        style={{
                          width: 4,
                          height: 4,
                          background: color,
                          flexShrink: 0,
                        }}
                      />
                    )}
                  </div>
                  <p className="ug-event__message">{evt.message}</p>
                  <div className="ug-event__meta">
                    {evt.wallet && (
                      <span style={{ color: "var(--color-accent)" }}>
                        {evt.wallet}
                      </span>
                    )}
                    <span>{evt.timestamp}</span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Quick access */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: "0.75rem",
          marginTop: "1rem",
        }}
      >
        {[
          {
            label: "Trace a Wallet",
            sub: "Start new trace",
            to: "/dashboard/trace",
            accent: "var(--color-accent)",
          },
          {
            label: "Open Cases",
            sub: "Manage investigations",
            to: "/dashboard/cases",
            accent: "var(--color-primary)",
          },
          {
            label: "Deposit Watch",
            sub: "Monitor cash-out",
            to: "/dashboard/deposit",
            accent: "var(--color-signal)",
          },
          {
            label: "Evidence Trail",
            sub: "Review court-ready data",
            to: "/dashboard/evidence",
            accent: "var(--color-primary)",
          },
        ].map((item) => (
          <button
            key={item.label}
            onClick={() => navigate({ to: item.to })}
            style={{
              padding: "1rem 1.1rem",
              textAlign: "left",
              cursor: "pointer",
              background: "var(--bg-1)",
              border: "1px solid var(--border-strong)",
              borderLeft: `2px solid ${item.accent}`,
              borderRadius: "4px",
              transition: "background 0.15s, transform 0.15s",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLElement).style.background =
                "oklch(0.155 0.022 258)";
              (e.currentTarget as HTMLElement).style.transform =
                "translateY(-1px)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLElement).style.background = "var(--bg-1)";
              (e.currentTarget as HTMLElement).style.transform =
                "translateY(0)";
            }}
          >
            <p
              style={{
                fontSize: "0.78rem",
                fontWeight: 700,
                color: "var(--color-foreground)",
                marginBottom: "0.3rem",
                letterSpacing: "-0.01em",
              }}
            >
              {item.label}
            </p>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-muted-foreground)",
                letterSpacing: "0.04em",
              }}
            >
              {item.sub}
            </p>
          </button>
        ))}
      </div>
    </>
  );
}
