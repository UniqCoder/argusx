import { createFileRoute, useNavigate } from "@tanstack/react-router";
import type { IntelEvent } from "@/lib/mock-data";
import { useAlerts } from "@/hooks/use-alerts";
import { useCases } from "@/hooks/use-cases";
import { useHealth } from "@/hooks/use-health";

export const Route = createFileRoute("/dashboard/")({
  component: CommandCenter,
});

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
  const { isLive } = useHealth();
  const criticalCount = allCases.filter(
    (c) => c.traceStatus === "critical",
  ).length;

  const stats = [
    {
      label: "Active Cases",
      value: allCases.filter((c) => c.traceStatus !== "closed").length,
    },
    {
      label: "Live Traces",
      value: allCases.filter((c) => c.traceStatus === "live-trace").length,
    },
    {
      label: "Network Signals",
      value: allCases.filter((c) => c.networkSignal !== "NONE").length,
    },
    {
      label: "Critical Alerts",
      value: criticalCount,
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
        <div
          className="ug-system-live"
          style={!isLive ? { color: "var(--color-muted-foreground)" } : undefined}
        >
          <span
            className="ug-system-live__dot"
            style={
              !isLive
                ? { background: "var(--color-muted-foreground)", boxShadow: "none" }
                : undefined
            }
          />
          {isLive ? "System Live" : "System Offline"}
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

      {/* Recent Activity — a glance at the alert feed, not a full copy of it */}
      <div className="ug-surface" style={{ overflow: "hidden" }}>
        <div className="ug-panel-header">
          <span className="ug-section-title" style={{ marginBottom: 0 }}>
            Recent Activity
          </span>
          <div className="ug-system-live" style={{ fontSize: "0.56rem" }}>
            <span className="ug-system-live__dot" />
            LIVE
          </div>
        </div>
        {events.length === 0 ? (
          <p
            style={{
              padding: "1rem 1.25rem",
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            No recent activity.
          </p>
        ) : (
          events.slice(0, 4).map((evt) => {
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
          })
        )}
        <button
          onClick={() => navigate({ to: "/dashboard/alerts" })}
          style={{
            width: "100%",
            padding: "0.6rem",
            background: "none",
            border: "none",
            borderTop: "1px solid var(--border-subtle)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.62rem",
            letterSpacing: "0.08em",
            color: "var(--color-accent)",
            cursor: "pointer",
          }}
        >
          VIEW ALL ALERTS →
        </button>
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
