import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import { useWalletRisk, formatRiskScore, RISK_TIER_COLOR } from "@/hooks/use-wallet";
import { useCaseContext } from "@/store/case-context-store";
import { WalletSelector } from "@/components/dashboard/WalletSelector";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import type { Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/risk")({
  component: RiskIntelligence,
});

// Single source of truth for tier -> label/color. Previously the dial's
// "Critical/High/Medium Risk" text was re-derived from score thresholds
// that (a) had no Low Risk case at all — any score under 55 read as
// "Medium Risk", including a genuine 0 — and (b) could disagree with the
// backend's own `risk_tier`, since it was a second, separately-tuned
// classification of the same number. This reads the tier the model itself
// assigned, the same value shown in the "Risk Tier" data row.
const TIER_META: Record<
  string,
  { label: string; color: string; badgeClass: string }
> = {
  critical: {
    label: "Critical Risk",
    color: RISK_TIER_COLOR["critical"]!,
    badgeClass: "ug-badge--critical",
  },
  high: {
    label: "High Risk",
    color: RISK_TIER_COLOR["high"]!,
    badgeClass: "ug-badge--high",
  },
  medium: {
    label: "Medium Risk",
    color: RISK_TIER_COLOR["medium"]!,
    badgeClass: "ug-badge--medium",
  },
  low: {
    label: "Low Risk",
    color: RISK_TIER_COLOR["low"]!,
    badgeClass: "ug-badge--low",
  },
  unknown: {
    label: "Unscored",
    color: RISK_TIER_COLOR["unknown"]!,
    badgeClass: "ug-badge--closed",
  },
};
const tierMeta = (tier: string | null) =>
  TIER_META[tier ?? ""] ?? TIER_META["unknown"]!;

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
        {formatRiskScore(score)}
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
  const { activeWallet, activeChain } = useCaseContext();

  // No fabricated demo wallet fallback — this page needs a real active
  // wallet (set by trace.tsx or cross-victim.tsx) to have anything to show.
  const walletToAnalyze = activeWallet;
  const chainToAnalyze = (activeChain || "ETH") as
    "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";

  const {
    riskScore: liveScore,
    riskTier,
    signals: liveSignals,
    loading,
    error,
  } = useWalletRisk(walletToAnalyze, chainToAnalyze as Chain);

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Intelligence</p>
          <h1 className="ug-page-header__title">Risk Intelligence</h1>
          <p className="ug-page-header__sub">
            {activeWallet
              ? `Analyzing: ${activeWallet.slice(0, 12)}...`
              : "Explainable risk analysis — every signal is backed by verifiable data. Trace or search a wallet first."}
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <WalletSelector />
          {liveScore !== null && (
            <span
              className={`ug-badge ${tierMeta(riskTier).badgeClass}`}
              style={{ fontSize: "0.62rem", padding: "0.3rem 0.7rem" }}
            >
              {(riskTier ?? "").toUpperCase() || "SCORED"}
            </span>
          )}
        </div>
      </div>

      {!activeWallet && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem" }}>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              color: "var(--color-muted-foreground)",
            }}
          >
            No wallet selected yet — trace a wallet or pick one from the
            selector above.
          </p>
        </div>
      )}

      {activeWallet && liveScore === null && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem" }}>
          {loading && !error && (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.62rem",
                color: "var(--color-muted-foreground)",
              }}
            >
              Scoring…
            </p>
          )}
          {/* The backend returns 200 with risk_tier="unknown" when it cannot
              score (explorer outage, or ML artifacts not provisioned in this
              environment) — an honest "no score", not an error. Say so.
              NEVER fabricate a score to fill this space. */}
          {!loading && !error && (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.62rem",
                color: "var(--color-muted-foreground)",
                lineHeight: 1.6,
              }}
            >
              {riskTier === "unknown"
                ? "ML risk artifacts are not provisioned in this environment — no score can be computed for this wallet. The backend returns an honest “unknown” rather than a fabricated number."
                : "No score available for this wallet."}
            </p>
          )}
          <BackendOfflineBanner error={error} context="risk score" />
        </div>
      )}

      {activeWallet && liveScore !== null && (
        <RiskPanel
          totalScore={liveScore}
          riskTier={riskTier}
          liveSignals={liveSignals}
          walletToAnalyze={walletToAnalyze}
          chainToAnalyze={chainToAnalyze}
          expanded={expanded}
          setExpanded={setExpanded}
        />
      )}
    </>
  );
}

// Split out so `totalScore` is a plain non-null number prop here — the
// parent only renders this once useWalletRisk has actually returned a score.
function RiskPanel({
  totalScore,
  riskTier,
  liveSignals,
  walletToAnalyze,
  chainToAnalyze,
  expanded,
  setExpanded,
}: {
  totalScore: number;
  riskTier: string | null;
  liveSignals: ReturnType<typeof useWalletRisk>["signals"];
  walletToAnalyze: string | null;
  chainToAnalyze: string;
  expanded: string | null;
  setExpanded: (id: string | null) => void;
}) {
  const meta = tierMeta(riskTier);
  const scoreColor = meta.color;
  // Sum of the DISPLAYED factors' SHAP magnitude — not the risk score.
  // These are two different units (a 0-100 model output vs. a normalized
  // 1-30 display scale for the top 5 features only); the old label claimed
  // the factors "total" the score, which was arithmetically false and, at
  // a score of 0, directly contradicted five visibly non-zero numbers on
  // screen.
  const totalContribution = liveSignals.reduce(
    (sum, s) => sum + s.contribution,
    0,
  );

  return (
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
            {chainToAnalyze}
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
            {meta.label}
          </p>
        </div>

        <div className="ug-divider" style={{ margin: "0 1.25rem" }} />

        <div style={{ padding: "0 1.25rem 1.25rem" }}>
          {[
            { k: "Wallet", v: walletToAnalyze ?? "—" },
            { k: "Chain", v: chainToAnalyze },
            { k: "Risk Tier", v: riskTier ?? "—" },
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
            {liveSignals.length} top contributing factors
          </span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
          {liveSignals.map((sig) => {
            const isOpen = expanded === sig.id;
            const increasesRisk = sig.direction === "increases_risk";
            // Colour communicates DIRECTION first, magnitude second — a
            // feature that decreases risk must never render in the same
            // red/orange language as one that increases it, no matter how
            // large its magnitude. Previously every factor used the same
            // magnitude-only red/amber/cyan scale and a bare "+N", so a
            // wallet whose top signals all REDUCED its score (this one)
            // displayed as a wall of red pluses — reading as five reasons
            // it's risky when it was the opposite.
            const barColor = increasesRisk
              ? sig.contribution > 20
                ? "var(--color-signal)"
                : "var(--color-primary)"
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
                      {totalContribution > 0
                        ? Math.round(
                            (sig.contribution / totalContribution) * 100,
                          )
                        : 0}
                      %
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
                    {increasesRisk ? "+" : "−"}
                    {sig.contribution}
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
                          {increasesRisk ? "Increases" : "Decreases"} risk ·{" "}
                          {totalContribution > 0
                            ? Math.round(
                                (sig.contribution / totalContribution) * 100,
                              )
                            : 0}
                          % of shown factors' weight
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
            {liveSignals.map((sig) => {
              const up = sig.direction === "increases_risk";
              return (
                <div
                  key={sig.id}
                  title={`${sig.label}: ${up ? "+" : "−"}${sig.contribution} (${up ? "increases" : "decreases"} risk)`}
                  style={{
                    flex: sig.contribution,
                    background: up
                      ? sig.contribution > 20
                        ? "var(--color-signal)"
                        : "var(--color-primary)"
                      : "var(--color-accent)",
                    opacity: 0.72,
                    transition: "opacity 0.15s",
                    cursor: "pointer",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.opacity = "1")}
                  onMouseLeave={(e) => (e.currentTarget.style.opacity = "0.72")}
                />
              );
            })}
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
              {formatRiskScore(totalScore)} / 100
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
