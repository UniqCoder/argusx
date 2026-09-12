import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { CaseSelector } from "@/components/dashboard/CaseSelector";
import { getCase, getCaseEvidence } from "@/lib/api";
import type { Case, EvidenceEvent } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/evidence")({
  component: EvidenceTrail,
});

const EVENT_META: Record<
  string,
  { title: string; icon: string; color: string }
> = {
  view_case: { title: "Case Viewed", icon: "V", color: "var(--color-muted-foreground)" },
  update_case_status: { title: "Case Status Updated", icon: "U", color: "var(--color-primary)" },
  export_pdf_report: { title: "Report Exported", icon: "R", color: "var(--color-primary)" },
  anchor_registered: { title: "Anchor Registered", icon: "A", color: "var(--color-accent)" },
  trace_completed: { title: "Trace Completed", icon: "T", color: "var(--color-accent)" },
  decision_issued: { title: "Decision Issued", icon: "D", color: "var(--color-signal)" },
};

function metaFor(evt: EvidenceEvent) {
  return (
    EVENT_META[evt.event_type] ?? {
      title: evt.event_type.replace(/_/g, " "),
      icon: evt.source === "ledger" ? "L" : "•",
      color: "var(--color-muted-foreground)",
    }
  );
}

// Every event_type carries different real fields in `details` — this picks
// the ones worth a one-line summary instead of dumping raw JSON.
function detailLine(evt: EvidenceEvent): string {
  const d = evt.details;
  switch (evt.event_type) {
    case "anchor_registered":
      return `${d["address"]} (${d["chain"]}) — attestation class ${d["attestation_class"]}, source: ${d["source_ref"]}`;
    case "trace_completed":
      return `${d["node_count"]} node(s) traced. Reproducible hash: ${String(d["reproducible_hash"] ?? "").slice(0, 16)}…`;
    case "decision_issued":
      return `Action: ${String(d["action"] ?? "").toUpperCase()} — ${d["reasoning"] ?? ""}`;
    case "update_case_status":
      return "Case status changed by an investigator.";
    case "export_pdf_report":
      return "Forensic PDF report generated for this case.";
    case "view_case":
      return "Case record opened by an investigator.";
    default:
      return Object.keys(d).length > 0 ? JSON.stringify(d) : "—";
  }
}

function EvidenceTrail() {
  const { activeCaseId, activeCaseNumber } = useCaseContext();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [events, setEvents] = useState<EvidenceEvent[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeCaseId) {
      setCaseData(null);
      setEvents([]);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    Promise.all([getCase(activeCaseId), getCaseEvidence(activeCaseId)])
      .then(([c, evts]) => {
        if (cancelled) return;
        setCaseData(c);
        setEvents(evts);
        setSelected(evts.length > 0 ? evts.length - 1 : null);
      })
      .catch((e) => {
        if (!cancelled) {
          setCaseData(null);
          setEvents([]);
          setError(e instanceof Error ? e.message : "Failed to load evidence");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCaseId]);

  const selectedEvent = selected != null ? events[selected] : undefined;

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Evidence</p>
          <h1 className="ug-page-header__title">Evidence Trail</h1>
          <p className="ug-page-header__sub">
            {activeCaseId
              ? `Trail for: ${activeCaseNumber ?? activeCaseId}`
              : "Chronological investigation log — every event is defensible and court-ready."}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <CaseSelector />
          {events.length > 0 && (
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-muted-foreground)",
                letterSpacing: "0.1em",
              }}
            >
              {events.length} events
            </span>
          )}
        </div>
      </div>

      {!activeCaseId && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            NO ACTIVE INVESTIGATION — select a case above to view its
            evidence trail.
          </p>
        </div>
      )}

      {activeCaseId && loading && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            Loading evidence…
          </p>
        </div>
      )}

      {activeCaseId && !loading && error && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-signal)",
            }}
          >
            Couldn't load this case's evidence — {error}
          </p>
        </div>
      )}

      {activeCaseId && !loading && !error && caseData && events.length === 0 && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-muted-foreground)",
              lineHeight: 1.6,
            }}
          >
            No evidence recorded yet for this case. Trace a wallet while this
            case is active (from Trace Wallet, or by opening the case first)
            to start building its real evidence trail — every anchor
            registered, trace run, and decision issued will append here.
          </p>
        </div>
      )}

      {activeCaseId && !loading && !error && events.length > 0 && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 300px",
            gap: "1rem",
            alignItems: "start",
          }}
        >
          {/* Timeline */}
          <div className="ug-surface" style={{ overflow: "hidden" }}>
            <div className="ug-panel-header">
              <span className="ug-section-title" style={{ marginBottom: 0 }}>
                {activeCaseNumber ?? activeCaseId} — Investigation Trail
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.56rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                APPEND-ONLY
              </span>
            </div>

            <div style={{ padding: "0.75rem 1.25rem" }}>
              <div className="ug-timeline">
                {events.map((evt, i) => {
                  const meta = metaFor(evt);
                  const isSelected = selected === i;
                  const time = new Date(evt.occurred_at).toLocaleString(
                    "en-IN",
                  );
                  return (
                    <div
                      key={i}
                      className="ug-timeline-event"
                      onClick={() => setSelected(i)}
                    >
                      <div
                        className="ug-timeline-event__dot"
                        style={{
                          borderColor: isSelected
                            ? meta.color
                            : "var(--border-strong)",
                          background: isSelected
                            ? `${meta.color.replace(")", " / 10%)")}`
                            : "var(--bg-0)",
                          boxShadow: isSelected
                            ? `0 0 0 2px ${meta.color.replace(")", " / 18%)")}`
                            : "none",
                        }}
                      >
                        <span style={{ fontSize: "0.6rem" }}>{meta.icon}</span>
                      </div>
                      <div className="ug-timeline-event__body">
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "baseline",
                            marginBottom: "0.2rem",
                          }}
                        >
                          <h3
                            style={{
                              fontSize: "0.8rem",
                              fontWeight: 600,
                              color: isSelected
                                ? meta.color
                                : "var(--color-foreground)",
                              letterSpacing: "-0.01em",
                            }}
                          >
                            {meta.title}
                          </h3>
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.58rem",
                              color: "var(--color-muted-foreground)",
                              flexShrink: 0,
                              marginLeft: "0.75rem",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {time}
                          </span>
                        </div>
                        <p
                          style={{
                            fontSize: "0.73rem",
                            color: "var(--color-muted-foreground)",
                            lineHeight: 1.5,
                            marginBottom: "0.3rem",
                            wordBreak: "break-word",
                          }}
                        >
                          {detailLine(evt)}
                        </p>
                        <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.58rem",
                              color: "var(--color-muted-foreground)",
                            }}
                          >
                            {evt.source === "ledger"
                              ? "Forensic engine ledger"
                              : "Audit log"}
                          </span>
                          {evt.actor && (
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: "0.58rem",
                                color: "var(--color-muted-foreground)",
                              }}
                            >
                              {evt.actor}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Inspector */}
          <div style={{ position: "sticky", top: 0 }}>
            {selectedEvent ? (
              <div className="ug-surface" style={{ overflow: "hidden" }}>
                <div
                  className="ug-panel-header"
                  style={{
                    borderLeft: `2px solid ${metaFor(selectedEvent).color}`,
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.56rem",
                      letterSpacing: "0.26em",
                      textTransform: "uppercase",
                      color: metaFor(selectedEvent).color,
                    }}
                  >
                    {selectedEvent.event_type.replace(/_/g, " ")}
                  </span>
                </div>

                <div style={{ padding: "1.1rem 1.25rem" }}>
                  <h3
                    style={{
                      fontSize: "0.9rem",
                      fontWeight: 700,
                      color: "var(--color-foreground)",
                      marginBottom: "1rem",
                      letterSpacing: "-0.02em",
                    }}
                  >
                    {metaFor(selectedEvent).title}
                  </h3>

                  {[
                    {
                      k: "Timestamp",
                      v: new Date(selectedEvent.occurred_at).toLocaleString("en-IN"),
                    },
                    { k: "Source", v: selectedEvent.source === "ledger" ? "Forensic ledger" : "Audit log" },
                    { k: "Actor", v: selectedEvent.actor ?? "—" },
                  ].map(({ k, v }) => (
                    <div key={k} className="ug-data-row">
                      <span className="ug-data-row__key">{k}</span>
                      <span className="ug-data-row__value">{v}</span>
                    </div>
                  ))}

                  <div className="ug-divider" />

                  <p className="ug-section-title">Details</p>
                  <pre
                    style={{
                      fontSize: "0.7rem",
                      color: "var(--color-foreground)",
                      lineHeight: 1.6,
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      fontFamily: "var(--font-mono)",
                      margin: 0,
                    }}
                  >
                    {JSON.stringify(selectedEvent.details, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <div
                className="ug-surface"
                style={{ padding: "2rem", textAlign: "center" }}
              >
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.64rem",
                    color: "var(--color-muted-foreground)",
                    letterSpacing: "0.08em",
                  }}
                >
                  SELECT AN EVENT TO INSPECT
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}
