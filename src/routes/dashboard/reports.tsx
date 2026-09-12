import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { getCase, getCaseReport } from "@/lib/api";
import { useCaseContext } from "@/store/case-context-store";
import { CaseSelector } from "@/components/dashboard/CaseSelector";
import type { Case } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/reports")({
  component: Reports,
});

function Reports() {
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  const { activeCaseId, activeCaseNumber } = useCaseContext();
  const [caseData, setCaseData] = useState<Case | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeCaseId) {
      setCaseData(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setLoadError(null);
    getCase(activeCaseId)
      .then((c) => {
        if (!cancelled) setCaseData(c);
      })
      .catch((e) => {
        if (!cancelled) {
          setCaseData(null);
          setLoadError(e instanceof Error ? e.message : "Failed to load case");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [activeCaseId]);

  const handleGenerate = async () => {
    if (!activeCaseId) return;
    setGenerating(true);
    setGenerated(false);
    setGenError(null);
    try {
      const blob = await getCaseReport(activeCaseId);
      const url = URL.createObjectURL(
        new Blob([blob], { type: "application/pdf" }),
      );
      const filename = `${activeCaseNumber ?? activeCaseId}_investigation_report.pdf`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 500);
      setGenerated(true);
    } catch (err) {
      // Never claim success on a genuine failure — surface it instead.
      setGenError(err instanceof Error ? err.message : "Report generation failed");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Evidence</p>
          <h1 className="ug-page-header__title">Reports</h1>
          <p className="ug-page-header__sub">
            {activeCaseId
              ? `Reporting on: ${activeCaseNumber ?? activeCaseId}`
              : "Court-ready investigation report generated from live case data."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <CaseSelector />
          <button
            className="ug-btn-primary"
            onClick={handleGenerate}
            disabled={generating || !activeCaseId}
            style={{ padding: "0.5rem 1rem", fontSize: "0.66rem" }}
          >
            {generating ? (
              <span
                style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
              >
                <span
                  style={{
                    width: "0.75rem",
                    height: "0.75rem",
                    border: "2px solid oklch(0.18 0.03 60 / 40%)",
                    borderTopColor: "oklch(0.18 0.03 60)",
                    borderRadius: "3px",
                    animation: "spin 0.65s linear infinite",
                    display: "inline-block",
                  }}
                />
                Generating…
              </span>
            ) : (
              "Generate PDF"
            )}
          </button>
        </div>
      </div>

      {generated && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.65rem 1rem",
            background: "oklch(0.83 0.14 205 / 6%)",
            border: "1px solid oklch(0.83 0.14 205 / 22%)",
            borderLeft: "2px solid var(--color-accent)",
            borderRadius: "2px",
            fontFamily: "var(--font-mono)",
            fontSize: "0.64rem",
            color: "var(--color-accent)",
            animation: "ug-check-in 0.3s ease both",
          }}
        >
          ✓ Report ready — {activeCaseNumber ?? activeCaseId}
          _investigation_report.pdf
        </div>
      )}

      {genError && (
        <div
          style={{
            marginBottom: "1rem",
            padding: "0.65rem 1rem",
            background: "oklch(0.64 0.22 18 / 8%)",
            border: "1px solid oklch(0.64 0.22 18 / 30%)",
            borderLeft: "2px solid var(--color-signal)",
            borderRadius: "2px",
            fontFamily: "var(--font-mono)",
            fontSize: "0.64rem",
            color: "var(--color-signal)",
          }}
        >
          ✗ Report generation failed — {genError}
        </div>
      )}

      {!activeCaseId && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            NO ACTIVE INVESTIGATION — select a case above before generating a
            report.
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

      {activeCaseId && !loading && loadError && (
        <div className="ug-surface" style={{ padding: "1.5rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.68rem",
              color: "var(--color-signal)",
            }}
          >
            Couldn't load this case — {loadError}
          </p>
        </div>
      )}

      {activeCaseId && !loading && caseData && (
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div
            style={{
              padding: "1.25rem 1.5rem",
              borderBottom: "1px solid var(--border-strong)",
              background: "var(--bg-2)",
            }}
          >
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.54rem",
                letterSpacing: "0.32em",
                textTransform: "uppercase",
                color: "var(--color-accent)",
                marginBottom: "0.35rem",
              }}
            >
              ARGUS INVESTIGATION REPORT
            </p>
            <h2
              style={{
                fontSize: "1.1rem",
                fontWeight: 700,
                letterSpacing: "-0.02em",
                color: "var(--color-foreground)",
              }}
            >
              {activeCaseNumber ?? caseData.id}
            </h2>
          </div>

          <div style={{ padding: "1.5rem" }}>
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
                <span
                  className="ug-data-row__value"
                  style={{
                    fontFamily: k === "Case ID" ? "var(--font-mono)" : undefined,
                  }}
                >
                  {v}
                </span>
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
              This page shows the case record available from the API. The
              full report — fund flow, hop-by-hop trace, risk analysis, VASP
              attribution — is assembled server-side from live case data by
              "Generate PDF" above; it isn't duplicated here as a preview to
              avoid showing content that could drift from what the PDF
              actually contains.
            </p>
          </div>
        </div>
      )}
    </>
  );
}
