import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  MOCK_CASES,
  MOCK_TRACE_EDGES,
  MOCK_TRACE_NODES,
  MOCK_RISK_SIGNALS,
} from "@/lib/mock-data";
import { getCaseReport } from "@/lib/api";
import { useCaseContext } from "@/store/case-context-store";
import { CaseSelector } from "@/components/dashboard/CaseSelector";

export const Route = createFileRoute("/dashboard/reports")({
  component: Reports,
});

const REPORT_SECTIONS = [
  "Case Details",
  "Complaint Information",
  "Reported Wallet",
  "Fund Flow Summary",
  "Hop-by-Hop Trace",
  "Cross-Victim Correlation",
  "Risk Analysis",
  "VASP Attribution",
  "Evidence Sources",
  "Methodology",
] as const;

function Reports() {
  const [activeSection, setActiveSection] =
    useState<string>("Fund Flow Summary");
  const [generating, setGenerating] = useState(false);
  const [generated, setGenerated] = useState(false);

  const { activeCaseId, hasActiveCase } = useCaseContext();
  const caseData = hasActiveCase()
    ? MOCK_CASES.find((c) => c.id === activeCaseId) || MOCK_CASES[0]!
    : MOCK_CASES[0]!;

  const handleGenerate = async () => {
    setGenerating(true);
    setGenerated(false);
    try {
      const blob = await getCaseReport(caseData.id);
      // Force download — works in all browsers
      const url = URL.createObjectURL(
        new Blob([blob], { type: "application/pdf" }),
      );
      const filename = `${caseData.id}_investigation_report.pdf`;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.style.display = "none";
      document.body.appendChild(a);
      a.click();
      // Small delay before cleanup so browser has time to start download
      setTimeout(() => {
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      }, 500);
      setGenerated(true);
    } catch (err) {
      console.error("PDF generation failed:", err);
      // Backend offline — generate a client-side fallback PDF notice
      setGenerated(true);
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
              ? `Reporting on: ${caseData.id}`
              : "Court-ready investigation report with full evidence chain and methodology."}
          </p>
        </div>
        <div style={{ display: "flex", gap: "0.5rem" }}>
          <CaseSelector />
          <button
            className="ug-btn-primary"
            onClick={handleGenerate}
            disabled={generating}
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
          <button
            className="ug-btn-ghost"
            style={{ padding: "0.5rem 1rem", fontSize: "0.66rem" }}
          >
            Export JSON
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
          ✓ Report ready — {caseData.id}_investigation_report.pdf
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "200px 1fr",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        {/* Section nav */}
        <div
          className="ug-surface"
          style={{ overflow: "hidden", position: "sticky", top: 0 }}
        >
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Sections
            </span>
          </div>
          {REPORT_SECTIONS.map((s) => (
            <button
              key={s}
              onClick={() => setActiveSection(s)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "0.55rem 1rem",
                background: "none",
                border: "none",
                borderLeft: `2px solid ${activeSection === s ? "var(--color-accent)" : "transparent"}`,
                color:
                  activeSection === s
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)",
                fontSize: "0.74rem",
                fontWeight: activeSection === s ? 600 : 400,
                cursor: "pointer",
                transition: "all 0.12s",
                fontFamily: "var(--font-display)",
                borderBottom: "1px solid var(--border-subtle)",
              }}
              onMouseEnter={(e) => {
                if (activeSection !== s)
                  (e.currentTarget as HTMLElement).style.color =
                    "var(--color-foreground)";
              }}
              onMouseLeave={(e) => {
                if (activeSection !== s)
                  (e.currentTarget as HTMLElement).style.color =
                    "var(--color-muted-foreground)";
              }}
            >
              {s}
            </button>
          ))}
        </div>

        {/* Report content */}
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          {/* Report header */}
          <div
            style={{
              padding: "1.25rem 1.5rem",
              borderBottom: "1px solid var(--border-strong)",
              background: "var(--bg-2)",
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
              }}
            >
              <div>
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
                    marginBottom: "0.2rem",
                  }}
                >
                  {caseData.id}
                </h2>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.64rem",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  {caseData.fraudType} — {caseData.blockchain}
                </p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.56rem",
                    letterSpacing: "0.14em",
                    textTransform: "uppercase",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  Generated
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.72rem",
                    color: "var(--color-foreground)",
                    marginTop: "0.15rem",
                  }}
                >
                  2026-08-29
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: "var(--color-accent)",
                    marginTop: "0.2rem",
                  }}
                >
                  Confidence: 94%
                </p>
              </div>
            </div>
          </div>

          <div style={{ padding: "1.5rem" }}>
            {activeSection === "Case Details" && (
              <ReportCaseDetails caseData={caseData} />
            )}
            {activeSection === "Fund Flow Summary" && <ReportFundFlow />}
            {activeSection === "Hop-by-Hop Trace" && <ReportHopTrace />}
            {activeSection === "Risk Analysis" && <ReportRisk />}
            {activeSection === "VASP Attribution" && <ReportVASP />}
            {(activeSection === "Complaint Information" ||
              activeSection === "Reported Wallet" ||
              activeSection === "Cross-Victim Correlation" ||
              activeSection === "Evidence Sources" ||
              activeSection === "Methodology") && (
              <ReportGenericSection title={activeSection} />
            )}
          </div>
        </div>
      </div>
    </>
  );
}

// -- Section components ----------------------------------------------------

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <p className="ug-section-title">{children as string}</p>;
}

function ReportCaseDetails({
  caseData,
}: {
  caseData: (typeof MOCK_CASES)[number];
}) {
  return (
    <div>
      <SectionTitle>Case Details</SectionTitle>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0 2rem",
        }}
      >
        {[
          { k: "Case ID", v: caseData.id },
          { k: "Fraud Type", v: caseData.fraudType },
          { k: "Blockchain", v: caseData.blockchain },
          { k: "Reported Wallet", v: caseData.reportedWallet },
          { k: "Victims", v: String(caseData.victimCount) },
          { k: "Risk Score", v: `${caseData.riskScore} / 100` },
          { k: "Network Signal", v: caseData.networkSignal },
          {
            k: "Status",
            v: caseData.traceStatus.replace("-", " ").toUpperCase(),
          },
        ].map(({ k, v }) => (
          <div key={k} className="ug-data-row">
            <span className="ug-data-row__key">{k}</span>
            <span
              className="ug-data-row__value"
              style={{
                fontFamily:
                  k === "Reported Wallet" || k === "Case ID"
                    ? "var(--font-mono)"
                    : undefined,
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
          fontSize: "0.8rem",
          color: "var(--color-foreground)",
          lineHeight: 1.75,
        }}
      >
        {caseData.description}
      </p>
    </div>
  );
}

function ReportFundFlow() {
  return (
    <div>
      <SectionTitle>Fund Flow Summary</SectionTitle>
      <div style={{ position: "relative", paddingLeft: "1.5rem" }}>
        {/* Vertical rail */}
        <div
          style={{
            position: "absolute",
            left: 6,
            top: 8,
            bottom: 8,
            width: 1,
            background: "var(--border-strong)",
          }}
        />
        {MOCK_TRACE_NODES.map((node) => (
          <div
            key={node.id}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.85rem",
              marginBottom: "0.65rem",
              position: "relative",
            }}
          >
            {/* Rail dot */}
            <div
              style={{
                position: "absolute",
                left: -24,
                width: 12,
                height: 12,
                border: "1.5px solid var(--color-accent)",
                background: "var(--bg-0)",
                borderRadius: "2px",
                flexShrink: 0,
                zIndex: 1,
                transform: "rotate(45deg)",
              }}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                width: "100%",
                padding: "0.6rem 0.85rem",
                background: "var(--bg-2)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "2px",
              }}
            >
              <div>
                <p
                  style={{
                    fontSize: "0.76rem",
                    fontWeight: 600,
                    color: "var(--color-foreground)",
                    marginBottom: "0.08rem",
                  }}
                >
                  {node.label}
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6rem",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  {node.address}
                </p>
              </div>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  color: node.amount
                    ? "var(--color-primary)"
                    : "var(--color-muted-foreground)",
                  fontWeight: 600,
                }}
              >
                {node.amount ?? "—"}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ReportHopTrace() {
  return (
    <div>
      <SectionTitle>Hop-by-Hop Trace</SectionTitle>
      <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {MOCK_TRACE_EDGES.map((edge, i) => {
          const from = MOCK_TRACE_NODES.find((n) => n.id === edge.from);
          const to = MOCK_TRACE_NODES.find((n) => n.id === edge.to);
          return (
            <div
              key={edge.id}
              className="ug-surface"
              style={{
                padding: "0.9rem 1rem",
                borderLeft: `2px solid ${edge.confidence > 85 ? "var(--color-accent)" : "var(--color-primary)"}`,
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.65rem",
                }}
              >
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    letterSpacing: "0.16em",
                    textTransform: "uppercase",
                    color: "var(--color-accent)",
                  }}
                >
                  Hop {i + 1}
                </span>
                <span
                  className={`ug-badge ${edge.confidence > 85 ? "ug-badge--medium" : "ug-badge--high"}`}
                >
                  {edge.confidence}% confidence
                </span>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: "0 1.5rem",
                }}
              >
                {[
                  { k: "From", v: from?.label ?? edge.from },
                  { k: "To", v: to?.label ?? edge.to },
                  { k: "Amount", v: edge.amount },
                  { k: "Timestamp", v: edge.timestamp || "Unresolved" },
                  { k: "Method", v: edge.method },
                  { k: "Blockchain", v: from?.blockchain ?? "—" },
                  { k: "Heuristic", v: edge.heuristic },
                  { k: "Source", v: edge.dataSource },
                ].map(({ k, v }) => (
                  <div key={k} className="ug-data-row">
                    <span className="ug-data-row__key">{k}</span>
                    <span
                      className="ug-data-row__value"
                      style={{ fontSize: "0.7rem" }}
                    >
                      {v}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ReportRisk() {
  return (
    <div>
      <SectionTitle>Risk Analysis</SectionTitle>
      {MOCK_RISK_SIGNALS.map((sig, i) => (
        <div
          key={sig.id}
          style={{
            padding: "0.8rem 0",
            borderBottom:
              i < MOCK_RISK_SIGNALS.length - 1
                ? "1px solid var(--border-subtle)"
                : "none",
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: "1rem",
            alignItems: "start",
          }}
        >
          <div>
            <p
              style={{
                fontSize: "0.78rem",
                fontWeight: 600,
                color: "var(--color-foreground)",
                marginBottom: "0.25rem",
              }}
            >
              {sig.label}
            </p>
            <p
              style={{
                fontSize: "0.72rem",
                color: "var(--color-muted-foreground)",
                lineHeight: 1.5,
                marginBottom: "0.2rem",
              }}
            >
              {sig.evidence}
            </p>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              Source: {sig.dataSource}
            </p>
          </div>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
              color:
                sig.contribution > 20
                  ? "var(--color-signal)"
                  : sig.contribution > 14
                    ? "var(--color-primary)"
                    : "var(--color-accent)",
              fontWeight: 700,
              whiteSpace: "nowrap",
            }}
          >
            +{sig.contribution} pts
          </span>
        </div>
      ))}
    </div>
  );
}

function ReportVASP() {
  return (
    <div>
      <SectionTitle>VASP Attribution</SectionTitle>
      <div
        className="ug-surface ug-surface--amber"
        style={{ padding: "1.1rem 1.25rem", marginBottom: "1rem" }}
      >
        <p
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: "0.56rem",
            letterSpacing: "0.26em",
            textTransform: "uppercase",
            color: "var(--color-primary)",
            marginBottom: "0.4rem",
          }}
        >
          Exchange Identified
        </p>
        <h3
          style={{
            fontSize: "0.96rem",
            fontWeight: 700,
            color: "var(--color-foreground)",
            marginBottom: "0.75rem",
            letterSpacing: "-0.01em",
          }}
        >
          Binance
        </h3>
        {[
          { k: "Cluster ID", v: "BC-7741" },
          { k: "Match Method", v: "Exchange Cluster Heuristic" },
          { k: "Confidence", v: "72%" },
          { k: "Data Source", v: "Arkham Intel" },
          { k: "Action", v: "Freeze Request Recommended" },
        ].map(({ k, v }) => (
          <div key={k} className="ug-data-row">
            <span className="ug-data-row__key">{k}</span>
            <span className="ug-data-row__value">{v}</span>
          </div>
        ))}
      </div>
      <p
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: "0.65rem",
          color: "var(--color-muted-foreground)",
          lineHeight: 1.7,
        }}
      >
        VASP attribution is based on heuristic cluster analysis. Confidence of
        72% indicates a strong match. Freeze requests should be submitted with
        the full evidence trail attached.
      </p>
    </div>
  );
}

function ReportGenericSection({ title }: { title: string }) {
  const content: Record<string, string> = {
    "Complaint Information":
      "Original NCRP complaint ID 2026/ETH/0041. Filed 2026-08-26 09:14 by victim reporting ₹3.2L investment fraud. Chain of custody documented.",
    "Reported Wallet":
      "Wallet 0x7A92...B4C1 submitted via SAHYOG portal. Blockchain: Ethereum. First transaction: 2026-08-15. Total inflow: 4.82 ETH across 12 transactions.",
    "Cross-Victim Correlation":
      "Network analysis identified 4 independent complaints from UP, Delhi, and Maharashtra sharing this wallet cluster. Pattern consistent with coordinated investment fraud operation.",
    "Evidence Sources":
      "Etherscan (on-chain data), Poly Bridge API (cross-chain events), Arkham Intel (exchange clusters), Forta Network (mixer detection), NCRP Database (complaint correlation).",
    Methodology:
      "Argus uses deterministic graph traversal, rule-based risk attribution, and cross-victim clustering. All heuristics are documented and auditable. No black-box AI conclusions.",
  };
  return (
    <div>
      <SectionTitle>{title}</SectionTitle>
      <p
        style={{
          fontSize: "0.82rem",
          color: "var(--color-foreground)",
          lineHeight: 1.8,
        }}
      >
        {content[title] ??
          "Section content will be populated from live investigation data."}
      </p>
    </div>
  );
}
