import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { MOCK_CASES } from "@/lib/mock-data";
import { useWalletRisk } from "@/hooks/use-wallet";
import { useCaseContext } from "@/store/case-context-store";
import { WalletSelector } from "@/components/dashboard/WalletSelector";
import type { Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/risk")({
  component: RiskIntelligence,
});

// -- Segmented arc score dial ----------------------------------------------

function ScoreDial({ score, color }: { score: number; color: string }) {
  const segments = 20;
  const filled = Math.round((score / 100) * segments);
  const r = 52;
  const cx = 68;
  const cy = 68;
  const startAngle = -220;
  const sweep = 260;

  const polarToXY = (angleDeg: number, radius: number) => {
    const rad = (angleDeg * Math.PI) / 180;
    return { x: cx + radius * Math.cos(rad), y: cy + radius * Math.sin(rad) };
  };

  const segAngle = sweep / segments;
  return (
    <svg width={136} height={110} viewBox="0 0 136 110">
      {Array.from({ length: segments }).map((_, i) => {
        const angle = startAngle + i * segAngle + segAngle * 0.1;
        const endAngle = angle + segAngle * 0.85;
        const p1 = polarToXY(angle, r - 7);
        const p2 = polarToXY(endAngle, r - 7);
        const p3 = polarToXY(endAngle, r);
        const p4 = polarToXY(angle, r);
        const isActive = i < filled;
        return (
          <path
            key={i}
            d={`M ${p1.x} ${p1.y} L ${p2.x} ${p2.y} L ${p3.x} ${p3.y} L ${p4.x} ${p4.y} Z`}
            fill={isActive ? color : "oklch(0.98 0 0 / 8%)"}
            style={{ transition: "fill 0.4s ease" }}
          />
        );
      })}
      <text
        x={cx}
        y={cy + 2}
        textAnchor="middle"
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 22,
          fontWeight: 700,
          fill: color,
          letterSpacing: "-0.04em",
        }}
      >
        {score}
      </text>
      <text
        x={cx}
        y={cy + 16}
        textAnchor="middle"
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 8,
          fill: "var(--color-muted-foreground)",
          letterSpacing: "0.1em",
        }}
      >
        / 100
      </text>
    </svg>
  );
}

// -- Page -----------------------------------------------------------------

function RiskIntelligence() {
  const [expanded, setExpanded] = useState<string | null>(null);
  const { activeWallet, activeChain, activeCaseId, hasActiveCase } =
    useCaseContext();

  // Fallback to first case if no case selected
  const caseData = hasActiveCase()
    ? MOCK_CASES.find((c) => c.id === activeCaseId) || MOCK_CASES[0]!
    : MOCK_CASES[0]!;

  const walletToAnalyze =
    activeWallet || caseData.reportedWallet.replace("...", "demo");
  const chainToAnalyze = (activeChain || "ETH") as
    "BTC" | "ETH" | "TRON" | "BSC" | "Polygon";

  const { riskScore: liveScore, signals: liveSignals } = useWalletRisk(
    walletToAnalyze,
    chainToAnalyze as Chain,
  );
  const totalScore = liveScore;
  const scoreColor =
    totalScore > 80
      ? "var(--color-signal)"
      : totalScore > 55
        ? "var(--color-primary)"
        : "var(--color-accent)";

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Intelligence</p>
          <h1 className="ug-page-header__title">Risk Intelligence</h1>
          <p className="ug-page-header__sub">
            {activeWallet
              ? `Analyzing: ${activeWallet.slice(0, 12)}...`
              : "Explainable risk analysis — every signal is backed by verifiable data."}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <WalletSelector />
          <span
            className="ug-badge ug-badge--critical"
            style={{ fontSize: "0.62rem", padding: "0.3rem 0.7rem" }}
          >
            {totalScore > 80
              ? "CRITICAL RISK"
              : totalScore > 55
                ? "HIGH RISK"
                : "MEDIUM RISK"}
          </span>
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "268px 1fr",
          gap: "1rem",
          alignItems: "start",
        }}
      >
        {/* Score panel */}
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Risk Score
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              {caseData.id}
            </span>
          </div>

          {/* Dial */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              padding: "1.5rem 1.25rem 0.75rem",
            }}
          >
            <ScoreDial score={totalScore} color={scoreColor} />
            <div style={{ width: "100%", marginTop: "0.75rem" }}>
              <div className="ug-risk-bar">
                <div
                  className="ug-risk-bar__fill"
                  style={{ width: `${totalScore}%`, background: scoreColor }}
                />
              </div>
            </div>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                letterSpacing: "0.22em",
                color: scoreColor,
                marginTop: "0.5rem",
                textTransform: "uppercase",
                fontWeight: 700,
              }}
            >
              {totalScore > 80
                ? "Critical Risk"
                : totalScore > 55
                  ? "High Risk"
                  : "Medium Risk"}
            </p>
          </div>

          <div className="ug-divider" style={{ margin: "0 1.25rem" }} />

          <div style={{ padding: "0 1.25rem 1.25rem" }}>
            {[
              { k: "Wallet", v: caseData.reportedWallet },
              { k: "Chain", v: caseData.blockchain },
              { k: "Fraud Type", v: caseData.fraudType },
              { k: "Victims", v: String(caseData.victimCount) },
            ].map(({ k, v }) => (
              <div key={k} className="ug-data-row">
                <span className="ug-data-row__key">{k}</span>
                <span
                  className="ug-data-row__value"
                  style={{
                    fontFamily: k === "Wallet" ? "var(--font-mono)" : undefined,
                    fontSize: "0.7rem",
                  }}
                >
                  {v}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Signals */}
        <div>
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "0.75rem",
            }}
          >
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              Contributing Signals
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              {liveSignals.length} factors — total {totalScore} pts
            </span>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
            {liveSignals.map((sig) => {
              const isOpen = expanded === sig.id;
              const barColor =
                sig.contribution > 20
                  ? "var(--color-signal)"
                  : sig.contribution > 14
                    ? "var(--color-primary)"
                    : "var(--color-accent)";
              return (
                <div
                  key={sig.id}
                  className="ug-surface"
                  style={{
                    overflow: "hidden",
                    borderLeft: `2px solid ${barColor}`,
                  }}
                >
                  <button
                    onClick={() => setExpanded(isOpen ? null : sig.id)}
                    style={{
                      width: "100%",
                      display: "grid",
                      gridTemplateColumns: "56px 1fr auto 28px",
                      alignItems: "center",
                      gap: "1rem",
                      padding: "0.85rem 1rem",
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                    }}
                  >
                    {/* Mini bar */}
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.25rem",
                      }}
                    >
                      <div className="ug-risk-bar">
                        <div
                          className="ug-risk-bar__fill"
                          style={{
                            width: `${(sig.contribution / 30) * 100}%`,
                            background: barColor,
                          }}
                        />
                      </div>
                      <span
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.54rem",
                          color: "var(--color-muted-foreground)",
                          letterSpacing: "0.08em",
                        }}
                      >
                        {Math.round((sig.contribution / totalScore) * 100)}%
                      </span>
                    </div>

                    {/* Label */}
                    <div>
                      <p
                        style={{
                          fontSize: "0.8rem",
                          fontWeight: 600,
                          color: "var(--color-foreground)",
                          marginBottom: "0.1rem",
                        }}
                      >
                        {sig.label}
                      </p>
                      <p
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.6rem",
                          color: "var(--color-muted-foreground)",
                        }}
                      >
                        {sig.evidence}
                      </p>
                    </div>

                    {/* Contribution */}
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.9rem",
                        fontWeight: 700,
                        color: barColor,
                        letterSpacing: "-0.02em",
                      }}
                    >
                      +{sig.contribution}
                    </span>

                    {/* Chevron */}
                    <span
                      style={{
                        color: "var(--color-muted-foreground)",
                        fontSize: "0.6rem",
                        transform: isOpen ? "rotate(180deg)" : "none",
                        transition: "transform 0.18s",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      ▾
                    </span>
                  </button>

                  {isOpen && (
                    <div
                      style={{
                        padding: "0 1rem 1rem",
                        borderTop: "1px solid var(--border-subtle)",
                        animation: "ug-check-in 0.18s ease both",
                      }}
                    >
                      <div
                        style={{
                          display: "grid",
                          gridTemplateColumns: "1fr 1fr",
                          gap: "1.25rem",
                          marginTop: "0.75rem",
                        }}
                      >
                        <div>
                          <p
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.56rem",
                              letterSpacing: "0.24em",
                              textTransform: "uppercase",
                              color: "var(--color-muted-foreground)",
                              marginBottom: "0.4rem",
                            }}
                          >
                            Supporting Data
                          </p>
                          <p
                            style={{
                              fontSize: "0.76rem",
                              color: "var(--color-foreground)",
                              lineHeight: 1.6,
                            }}
                          >
                            {sig.detail}
                          </p>
                        </div>
                        <div>
                          <p
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.56rem",
                              letterSpacing: "0.24em",
                              textTransform: "uppercase",
                              color: "var(--color-muted-foreground)",
                              marginBottom: "0.4rem",
                            }}
                          >
                            Data Source
                          </p>
                          <p
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.76rem",
                              color: barColor,
                              marginBottom: "0.5rem",
                            }}
                          >
                            {sig.dataSource}
                          </p>
                          <p
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.58rem",
                              color: "var(--color-muted-foreground)",
                            }}
                          >
                            {sig.contribution} of {totalScore} pts (
                            {Math.round((sig.contribution / totalScore) * 100)}
                            %)
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Composition bar */}
          <div
            className="ug-surface"
            style={{ padding: "1rem 1.25rem", marginTop: "0.75rem" }}
          >
            <span className="ug-section-title">Score Composition</span>
            <div
              style={{
                display: "flex",
                height: 8,
                borderRadius: 0,
                overflow: "hidden",
                gap: 2,
              }}
            >
              {liveSignals.map((sig) => (
                <div
                  key={sig.id}
                  title={`${sig.label}: +${sig.contribution}`}
                  style={{
                    flex: sig.contribution,
                    background:
                      sig.contribution > 20
                        ? "var(--color-signal)"
                        : sig.contribution > 14
                          ? "var(--color-primary)"
                          : "var(--color-accent)",
                    opacity: 0.72,
                    transition: "opacity 0.15s",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.72")}
                />
              ))}
            </div>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                marginTop: "0.4rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.56rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                0
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.56rem",
                  color: scoreColor,
                  fontWeight: 700,
                }}
              >
                {totalScore} / 100
              </span>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
