import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import type { IntelEvent } from "@/lib/mock-data";
import { useAlerts } from "@/hooks/use-alerts";
import { useCaseContext } from "@/store/case-context-store";
import { MOCK_CASES } from "@/lib/mock-data";

export const Route = createFileRoute("/dashboard/alerts")({
  component: LiveAlerts,
});

const SEV_COLOR: Record<IntelEvent["severity"], string> = {
  CRITICAL: "var(--color-signal)",
  HIGH: "var(--color-primary)",
  MEDIUM: "var(--color-accent)",
  LOW: "var(--color-muted-foreground)",
  INFO: "var(--color-muted-foreground)",
};

const SEV_BADGE: Record<IntelEvent["severity"], string> = {
  CRITICAL: "ug-badge--critical",
  HIGH: "ug-badge--high",
  MEDIUM: "ug-badge--medium",
  LOW: "ug-badge--low",
  INFO: "ug-badge--closed",
};

function LiveAlerts() {
  const { events, setEvents } = useAlerts();
  const [filter, setFilter] = useState<string>("All");
  const navigate = useNavigate();
  const { setActiveCase } = useCaseContext();

  const acknowledge = (id: string) =>
    setEvents((prev) =>
      prev.map((e) => (e.id === id ? { ...e, read: true } : e)),
    );

  const handleOpenAlert = (evt: IntelEvent) => {
    // Find the case in mock data to get full details
    const caseData = MOCK_CASES.find((c) => c.id === evt.caseId);
    if (caseData) {
      setActiveCase({
        caseId: caseData.id,
        caseNumber: caseData.id,
        wallet: caseData.reportedWallet,
        chain: caseData.blockchain as
          "BTC" | "ETH" | "TRON" | "BSC" | "Polygon",
        fraudType: caseData.fraudType,
        status: caseData.traceStatus,
      });
    }
    // Navigate to investigation
    navigate({ to: "/dashboard/investigation" });
  };

  const filtered =
    filter === "All" ? events : events.filter((e) => e.severity === filter);
  const unread = events.filter((e) => !e.read).length;

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Operations</p>
          <h1 className="ug-page-header__title">Live Alerts</h1>
          <p className="ug-page-header__sub">
            Operational intelligence timeline — real-time signals from active
            traces.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
          {unread > 0 && (
            <div
              style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
            >
              <div
                style={{
                  width: 6,
                  height: 6,
                  background: "var(--color-signal)",
                }}
              />
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-signal)",
                  letterSpacing: "0.12em",
                }}
              >
                {unread} UNREAD
              </span>
            </div>
          )}
          <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
            <span className="ug-system-live__dot" />
            LIVE
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="ug-pills">
        {["All", "CRITICAL", "HIGH", "MEDIUM", "INFO"].map((f) => (
          <button
            key={f}
            className={`ug-pill${filter === f ? " is-active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Alert list */}
      <div className="ug-surface" style={{ overflow: "hidden" }}>
        {filtered.map((evt, i) => {
          const color = SEV_COLOR[evt.severity];
          const isLast = i === filtered.length - 1;
          return (
            <div
              key={evt.id}
              style={{
                display: "grid",
                gridTemplateColumns: "3px 1fr auto",
                gap: "1rem",
                padding: "1rem 1.25rem",
                borderBottom: isLast
                  ? "none"
                  : "1px solid var(--border-subtle)",
                background: !evt.read
                  ? `${color.replace(")", " / 3.5%)")}`
                  : "transparent",
                alignItems: "start",
                transition: "background 0.15s",
              }}
              onMouseEnter={(e) => {
                if (evt.read)
                  (e.currentTarget as HTMLElement).style.background =
                    "oklch(0.98 0 0 / 2%)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.background = !evt.read
                  ? `${color.replace(")", " / 3.5%)")}`
                  : "transparent";
              }}
            >
              {/* Severity rail */}
              <div
                style={{
                  background: color,
                  alignSelf: "stretch",
                  borderRadius: 0,
                  width: "3px",
                }}
              />

              {/* Content */}
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.6rem",
                    marginBottom: "0.45rem",
                    flexWrap: "wrap",
                  }}
                >
                  <span className={`ug-badge ${SEV_BADGE[evt.severity]}`}>
                    {evt.severity}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.58rem",
                      letterSpacing: "0.2em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {evt.type}
                  </span>
                  {!evt.read && (
                    <span
                      style={{
                        width: 4,
                        height: 4,
                        background: color,
                        display: "inline-block",
                      }}
                    />
                  )}
                </div>
                <p
                  style={{
                    fontSize: "0.82rem",
                    color: "var(--color-foreground)",
                    lineHeight: 1.5,
                    marginBottom: "0.4rem",
                  }}
                >
                  {evt.message}
                </p>
                <div
                  style={{ display: "flex", gap: "1.25rem", flexWrap: "wrap" }}
                >
                  {evt.wallet && (
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.6rem",
                        color: "var(--color-accent)",
                      }}
                    >
                      {evt.wallet}
                    </span>
                  )}
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {evt.caseId}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {evt.timestamp}
                  </span>
                </div>
              </div>

              {/* Actions — compact row */}
              <div
                style={{
                  display: "flex",
                  gap: "0.4rem",
                  flexShrink: 0,
                  alignItems: "flex-start",
                  paddingTop: "0.1rem",
                }}
              >
                <button
                  className="ug-btn-primary"
                  onClick={() => handleOpenAlert(evt)}
                  style={{
                    padding: "0.3rem 0.75rem",
                    fontSize: "0.6rem",
                    whiteSpace: "nowrap",
                  }}
                >
                  Open
                </button>
                {!evt.read && (
                  <button
                    className="ug-btn-ghost"
                    onClick={() => acknowledge(evt.id)}
                    style={{ padding: "0.28rem 0.65rem", fontSize: "0.6rem" }}
                  >
                    Ack
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
