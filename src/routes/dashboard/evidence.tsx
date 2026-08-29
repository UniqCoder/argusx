import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  MOCK_EVIDENCE_TRAIL,
  type EvidenceEvent,
  MOCK_CASES,
} from "@/lib/mock-data";
import { useCaseContext } from "@/store/case-context-store";
import { CaseSelector } from "@/components/dashboard/CaseSelector";

export const Route = createFileRoute("/dashboard/evidence")({
  component: EvidenceTrail,
});

const TYPE_COLOR: Record<EvidenceEvent["type"], string> = {
  complaint: "var(--color-primary)",
  report: "var(--color-primary)",
  trace: "var(--color-accent)",
  hop: "var(--color-accent)",
  "cross-chain": "var(--color-primary)",
  signal: "var(--color-signal)",
  vasp: "var(--color-primary)",
  evidence: "var(--color-accent)",
};

const TYPE_ICON: Record<EvidenceEvent["type"], string> = {
  complaint: "C",
  report: "R",
  trace: "T",
  hop: "H",
  "cross-chain": "X",
  signal: "S",
  vasp: "V",
  evidence: "E",
};

function EvidenceTrail() {
  const [selected, setSelected] = useState<string | null>("ev9");
  const { activeCaseId, hasActiveCase } = useCaseContext();

  // Use active case if available, otherwise fallback to mock
  const caseData = hasActiveCase()
    ? MOCK_CASES.find((c) => c.id === activeCaseId) || MOCK_CASES[0]!
    : MOCK_CASES[0]!;

  const selectedEvent = MOCK_EVIDENCE_TRAIL.find((e) => e.id === selected);

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Evidence</p>
          <h1 className="ug-page-header__title">Evidence Trail</h1>
          <p className="ug-page-header__sub">
            {activeCaseId
              ? `Trail for: ${caseData.id}`
              : "Chronological investigation log — every event is defensible and court-ready."}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <CaseSelector />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.6rem",
              color: "var(--color-muted-foreground)",
              letterSpacing: "0.1em",
            }}
          >
            {MOCK_EVIDENCE_TRAIL.length} events
          </span>
        </div>
      </div>

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
              UG-2026-04821 � Investigation Trail
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
              {MOCK_EVIDENCE_TRAIL.map((evt) => {
                const color = TYPE_COLOR[evt.type];
                const isSelected = selected === evt.id;
                return (
                  <div
                    key={evt.id}
                    className="ug-timeline-event"
                    onClick={() => setSelected(evt.id)}
                  >
                    {/* Dot */}
                    <div
                      className="ug-timeline-event__dot"
                      style={{
                        borderColor: isSelected
                          ? color
                          : "var(--border-strong)",
                        background: isSelected
                          ? `${color.replace(")", " / 10%)")}`
                          : "var(--bg-0)",
                        boxShadow: isSelected
                          ? `0 0 0 2px ${color.replace(")", " / 18%)")}`
                          : "none",
                      }}
                    >
                      <span style={{ fontSize: "0.6rem" }}>
                        {TYPE_ICON[evt.type]}
                      </span>
                    </div>

                    {/* Body */}
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
                              ? color
                              : "var(--color-foreground)",
                            letterSpacing: "-0.01em",
                          }}
                        >
                          {evt.title}
                        </h3>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.58rem",
                            color: "var(--color-muted-foreground)",
                            flexShrink: 0,
                            marginLeft: "0.75rem",
                          }}
                        >
                          {evt.timestamp.split(" ")[1] ?? evt.timestamp}
                        </span>
                      </div>
                      <p
                        style={{
                          fontSize: "0.73rem",
                          color: "var(--color-muted-foreground)",
                          lineHeight: 1.5,
                          marginBottom: "0.3rem",
                        }}
                      >
                        {evt.detail}
                      </p>
                      <div
                        style={{
                          display: "flex",
                          gap: "1rem",
                          flexWrap: "wrap",
                        }}
                      >
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.58rem",
                            color: "var(--color-muted-foreground)",
                          }}
                        >
                          {evt.dataSource}
                        </span>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.58rem",
                            color:
                              evt.confidence > 90
                                ? "var(--color-accent)"
                                : evt.confidence > 70
                                  ? "var(--color-primary)"
                                  : "var(--color-muted-foreground)",
                          }}
                        >
                          {evt.confidence}% conf
                        </span>
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
                  borderLeft: `2px solid ${TYPE_COLOR[selectedEvent.type]}`,
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.56rem",
                      letterSpacing: "0.26em",
                      textTransform: "uppercase",
                      color: TYPE_COLOR[selectedEvent.type],
                    }}
                  >
                    {selectedEvent.type.replace("-", " ")}
                  </span>
                </div>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  {selectedEvent.confidence}% conf
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
                    lineHeight: 1.3,
                  }}
                >
                  {selectedEvent.title}
                </h3>

                {[
                  { k: "Timestamp", v: selectedEvent.timestamp },
                  { k: "Method", v: selectedEvent.method },
                  { k: "Data Source", v: selectedEvent.dataSource },
                  { k: "Confidence", v: `${selectedEvent.confidence}%` },
                ].map(({ k, v }) => (
                  <div key={k} className="ug-data-row">
                    <span className="ug-data-row__key">{k}</span>
                    <span className="ug-data-row__value">{v}</span>
                  </div>
                ))}

                <div className="ug-divider" />

                <p className="ug-section-title">Supporting Evidence</p>
                <p
                  style={{
                    fontSize: "0.76rem",
                    color: "var(--color-foreground)",
                    lineHeight: 1.65,
                    marginBottom: "1rem",
                  }}
                >
                  {selectedEvent.detail}
                </p>

                {/* Confidence bar */}
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                  }}
                >
                  <div className="ug-risk-bar" style={{ flex: 1 }}>
                    <div
                      className="ug-risk-bar__fill"
                      style={{
                        width: `${selectedEvent.confidence}%`,
                        background: TYPE_COLOR[selectedEvent.type],
                      }}
                    />
                  </div>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      color: TYPE_COLOR[selectedEvent.type],
                      fontWeight: 700,
                      flexShrink: 0,
                    }}
                  >
                    {selectedEvent.confidence}%
                  </span>
                </div>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.56rem",
                    color: "var(--color-muted-foreground)",
                    marginTop: "0.3rem",
                  }}
                >
                  {selectedEvent.dataSource}
                </p>
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
    </>
  );
}
