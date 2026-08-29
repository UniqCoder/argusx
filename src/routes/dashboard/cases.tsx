import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import type { CaseStatus } from "@/lib/mock-data";
import { useCases } from "@/hooks/use-cases";
import { useCaseContext } from "@/store/case-context-store";

export const Route = createFileRoute("/dashboard/cases")({
  component: Cases,
});

const FILTERS = [
  "All",
  "Live Trace",
  "Network Signal",
  "VASP Identified",
  "Critical",
  "Evidence Ready",
] as const;

const STATUS_LABEL: Record<CaseStatus, string> = {
  "live-trace": "Live Trace",
  "network-signal": "Network Signal",
  "vasp-identified": "VASP Identified",
  critical: "Critical",
  "evidence-ready": "Evidence Ready",
  closed: "Closed",
};

const STATUS_BADGE: Record<CaseStatus, string> = {
  "live-trace": "ug-badge--live",
  "network-signal": "ug-badge--medium",
  "vasp-identified": "ug-badge--high",
  critical: "ug-badge--critical",
  "evidence-ready": "ug-badge--medium",
  closed: "ug-badge--closed",
};

const SIGNAL_BADGE: Record<string, string> = {
  HIGH: "ug-badge--critical",
  MEDIUM: "ug-badge--high",
  LOW: "ug-badge--medium",
  NONE: "ug-badge--closed",
};

function RiskBar({ value }: { value: number }) {
  const color =
    value > 80
      ? "var(--color-signal)"
      : value > 55
        ? "var(--color-primary)"
        : "var(--color-accent)";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div className="ug-risk-bar" style={{ width: 52 }}>
        <div
          className="ug-risk-bar__fill"
          style={{ width: `${value}%`, background: color }}
        />
      </div>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.64rem",
          color,
          minWidth: 24,
          fontWeight: 700,
        }}
      >
        {value}
      </span>
    </div>
  );
}

function Cases() {
  const [filter, setFilter] = useState<string>("All");
  const navigate = useNavigate();
  const { cases: filtered, allCases, loading } = useCases(filter);
  const { setActiveCase } = useCaseContext();

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Investigate</p>
          <h1 className="ug-page-header__title">Cases</h1>
          <p className="ug-page-header__sub">
            Active investigation management — click any row to open the
            workspace.
          </p>
        </div>
        <button
          className="ug-btn-primary"
          onClick={() => navigate({ to: "/dashboard/trace" })}
          style={{
            padding: "0.55rem 1.1rem",
            fontSize: "0.68rem",
            whiteSpace: "nowrap",
          }}
        >
          + New Trace
        </button>
      </div>

      {/* Filter pills */}
      <div className="ug-pills">
        {FILTERS.map((f) => (
          <button
            key={f}
            className={`ug-pill${filter === f ? " is-active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f}
            {f === "Critical" && (
              <span
                style={{
                  marginLeft: "0.35rem",
                  width: 4,
                  height: 4,
                  background: "var(--color-signal)",
                  display: "inline-block",
                  verticalAlign: "middle",
                }}
              />
            )}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="ug-surface" style={{ overflow: "hidden" }}>
        {/* Header */}
        <div className="ug-case-row ug-case-row__header">
          <span>Case ID</span>
          <span>Fraud Type</span>
          <span>Chain</span>
          <span>Status</span>
          <span>Signal</span>
          <span>Risk</span>
          <span>Activity</span>
        </div>

        {loading && filtered.length === 0 && (
          <div
            style={{
              padding: "2rem",
              textAlign: "center",
              fontFamily: "var(--font-mono)",
              fontSize: "0.64rem",
              color: "var(--color-muted-foreground)",
              letterSpacing: "0.1em",
            }}
          >
            LOADING CASES...
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <div
            style={{
              padding: "3rem",
              textAlign: "center",
              fontFamily: "var(--font-mono)",
              fontSize: "0.7rem",
              color: "var(--color-muted-foreground)",
              letterSpacing: "0.1em",
            }}
          >
            NO CASES MATCH THIS FILTER
          </div>
        )}

        {filtered.map((c) => (
          <div
            key={c.id}
            className="ug-case-row"
            onClick={() => {
              // Set case context so other pages see this case
              setActiveCase({
                caseId: c.id,
                caseNumber: c.id,
                wallet: c.reportedWallet,
                chain: c.blockchain as
                  "BTC" | "ETH" | "TRON" | "BSC" | "Polygon",
                fraudType: c.fraudType,
                status: c.traceStatus,
              });
              navigate({ to: "/dashboard/investigation" });
            }}
            title={c.description}
          >
            {/* Case ID */}
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-accent)",
                letterSpacing: "0.04em",
              }}
            >
              {c.id}
            </span>

            {/* Fraud type + wallet */}
            <div>
              <p
                style={{
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  color: "var(--color-foreground)",
                  marginBottom: "0.08rem",
                  letterSpacing: "-0.01em",
                }}
              >
                {c.fraudType}
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-muted-foreground)",
                  letterSpacing: "0.04em",
                }}
              >
                {c.reportedWallet}
              </p>
            </div>

            {/* Chain */}
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              {c.blockchain}
            </span>

            {/* Status */}
            <span className={`ug-badge ${STATUS_BADGE[c.traceStatus]}`}>
              {STATUS_LABEL[c.traceStatus]}
            </span>

            {/* Network signal */}
            <span className={`ug-badge ${SIGNAL_BADGE[c.networkSignal]}`}>
              {c.networkSignal}
            </span>

            {/* Risk bar */}
            <RiskBar value={c.riskScore} />

            {/* Activity */}
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.62rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              {c.lastActivity}
            </span>
          </div>
        ))}
      </div>

      {/* Footer */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: "0.85rem",
          padding: "0 0.25rem",
        }}
      >
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            color: "var(--color-muted-foreground)",
            letterSpacing: "0.08em",
          }}
        >
          {filtered.length} case{filtered.length !== 1 ? "s" : ""} —{" "}
          {allCases.filter((c) => c.traceStatus === "critical").length} critical
        </p>
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.6rem",
            color: "var(--color-muted-foreground)",
            letterSpacing: "0.08em",
          }}
        >
          SORTED BY RISK — DESCENDING
        </p>
      </div>
    </>
  );
}
