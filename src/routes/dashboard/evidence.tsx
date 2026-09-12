import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { CaseSelector } from "@/components/dashboard/CaseSelector";
import { getCase } from "@/lib/api";
import type { Case } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/evidence")({
  component: EvidenceTrail,
});

function EvidenceTrail() {
  const { activeCaseId, activeCaseNumber } = useCaseContext();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeCaseId) {
      setCaseData(null);
      return;
    }
    // activeCaseId is displayed as "UG-XXXXXXXX" but the real backend id
    // is the raw case id — CaseSelector stores the raw id as caseNumber
    // is equal to caseId here, so use it directly.
    let cancelled = false;
    setLoading(true);
    setError(null);
    getCase(activeCaseId)
      .then((c) => {
        if (!cancelled) setCaseData(c);
      })
      .catch((e) => {
        if (!cancelled) {
          setCaseData(null);
          setError(e instanceof Error ? e.message : "Failed to load case");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCaseId]);

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
            Loading case…
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
            Couldn't load this case — {error}
          </p>
        </div>
      )}

      {activeCaseId && !loading && caseData && (
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Case Record
            </span>
          </div>
          <div style={{ padding: "1.1rem 1.25rem" }}>
            {[
              { k: "Case ID", v: caseData.id },
              { k: "Status", v: caseData.status },
              {
                k: "Assigned Investigator",
                v: caseData.assigned_investigator ?? "Unassigned",
              },
              {
                k: "Opened",
                v: new Date(caseData.opened_at).toLocaleString("en-IN"),
              },
              {
                k: "Closed",
                v: caseData.closed_at
                  ? new Date(caseData.closed_at).toLocaleString("en-IN")
                  : "—",
              },
            ].map(({ k, v }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span className="ug-data-row__value">{v}</span>
              </div>
            ))}

            <div className="ug-divider" />

            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.66rem",
                color: "var(--color-muted-foreground)",
                lineHeight: 1.7,
              }}
            >
              A chronological, append-only event timeline (complaint →
              trace → correlation → VASP attribution) requires a
              case-scoped audit endpoint the backend doesn't expose yet.
              Rather than show fabricated events, this section is left
              empty until that endpoint exists — see the case's linked
              alerts and cross-victim correlation on their own pages for
              the evidence available today.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
