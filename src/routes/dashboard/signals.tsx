import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useCorrelation } from "@/hooks/use-correlation";
import { useCaseContext } from "@/store/case-context-store";
import { WalletSelector } from "@/components/dashboard/WalletSelector";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import type { Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/signals")({
  component: NetworkSignals,
});

// ── Page ─────────────────────────────────────────────────────────────────

function NetworkSignals() {
  const navigate = useNavigate();
  const { activeWallet, activeChain, setActiveWallet } = useCaseContext();
  const chainToUse = (activeChain || "ETH") as Chain;

  const {
    signal: sig,
    linkedComplaints,
    loading,
    error,
  } = useCorrelation(activeWallet, chainToUse);

  const daysActive = (() => {
    if (linkedComplaints.length === 0) return 0;
    const earliest = Math.min(
      ...linkedComplaints.map((c) => new Date(c.filed_at).getTime()),
    );
    return Math.max(0, Math.round((Date.now() - earliest) / 86_400_000));
  })();

  return (
    <>
      {/* Page header — badge sits inline at end, aligned to bottom */}
      <div className="ug-page-header" style={{ alignItems: "flex-end" }}>
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Intelligence</p>
          <h1 className="ug-page-header__title">Network Signals</h1>
          <p className="ug-page-header__sub">
            {activeWallet
              ? `Correlating: ${activeWallet.slice(0, 12)}...`
              : "Cross-victim correlation — same blockchain infrastructure, multiple independent fraud complaints."}
          </p>
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
            flexShrink: 0,
            marginBottom: "0.25rem",
          }}
        >
          <WalletSelector />
          {sig && (
            <span
              className="ug-badge ug-badge--critical"
              style={{ fontSize: "0.6rem", padding: "0.28rem 0.65rem" }}
            >
              Signal: {sig.signalStrength}
            </span>
          )}
        </div>
      </div>

      {!activeWallet && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "1rem" }}>
          <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
            No wallet selected yet — trace a wallet or pick one from the selector above.
          </p>
        </div>
      )}

      {activeWallet && !sig && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "1rem" }}>
          {loading && !error && (
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
              Correlating…
            </p>
          )}
          <BackendOfflineBanner error={error} context="network signal" />
        </div>
      )}

      {sig && (
        <>
          {/* Signal detection banner */}
          <div className="ug-surface ug-surface--critical" style={{ marginBottom: "1rem" }}>
            <div className="ug-panel-header">
              <div>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.54rem",
                    letterSpacing: "0.3em",
                    textTransform: "uppercase",
                    color: "var(--color-signal)",
                    marginBottom: "0.3rem",
                  }}
                >
                  NETWORK SIGNAL DETECTED
                </p>
                <h2
                  style={{
                    fontSize: "1rem",
                    fontWeight: 700,
                    letterSpacing: "-0.02em",
                    color: "var(--color-foreground)",
                    fontFamily: "var(--font-mono)",
                  }}
                >
                  {sig.wallet}
                </h2>
              </div>
              <button
                className="ug-btn-primary"
                onClick={() => {
                  if (activeWallet) setActiveWallet(activeWallet, chainToUse);
                  navigate({ to: "/dashboard/investigation" });
                }}
                style={{
                  padding: "0.45rem 1rem",
                  fontSize: "0.66rem",
                  flexShrink: 0,
                }}
              >
                Open Investigation
              </button>
            </div>

            {/* Stats grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(4, 1fr)",
                borderTop: "1px solid var(--border-strong)",
              }}
            >
              {[
                {
                  label: "Independent Victims",
                  value: sig.victims,
                  color: "var(--color-signal)",
                },
                {
                  label: "Related Complaints",
                  value: sig.complaints,
                  color: "var(--color-primary)",
                },
                {
                  label: "States Affected",
                  value: sig.states,
                  color: "var(--color-accent)",
                },
                {
                  label: "Days Active",
                  value: daysActive,
                  color: "var(--color-foreground)",
                },
              ].map((s) => (
                <div
                  key={s.label}
                  style={{
                    padding: "1rem 1.1rem",
                    background: "var(--bg-2)",
                    borderRight: "1px solid var(--border-strong)",
                    borderTop: `2px solid ${s.color}`,
                  }}
                >
                  <p
                    style={{
                      fontSize: "1.85rem",
                      fontWeight: 700,
                      letterSpacing: "-0.05em",
                      color: s.color,
                      lineHeight: 1,
                    }}
                  >
                    {s.value}
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.54rem",
                      letterSpacing: "0.16em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                      marginTop: "0.3rem",
                    }}
                  >
                    {s.label}
                  </p>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div
              style={{
                padding: "0.75rem 1.25rem",
                borderTop: "1px solid var(--border-strong)",
                display: "flex",
                alignItems: "center",
                gap: "0.75rem",
              }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.62rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                Funds at risk:
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  color: "var(--color-primary)",
                }}
              >
                {sig.totalFundsAtRisk}
              </span>
            </div>
          </div>

          {/* Linked complaints — the real correlation result, not a
              hardcoded graph or a slice of unrelated case data. */}
          <div className="ug-surface" style={{ overflow: "hidden" }}>
            <div className="ug-panel-header">
              <span className="ug-section-title" style={{ marginBottom: 0 }}>
                Linked Complaints
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.56rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                {linkedComplaints.length} matched
              </span>
            </div>
            {linkedComplaints.length === 0 && (
              <p
                style={{
                  padding: "1rem 1.25rem",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.62rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                No linked complaints found for this wallet.
              </p>
            )}
            {linkedComplaints.map((c, i) => (
              <div
                key={c.id}
                className="ug-event"
                style={{
                  borderBottom:
                    i < linkedComplaints.length - 1
                      ? "1px solid var(--border-subtle)"
                      : "none",
                }}
              >
                <div
                  className="ug-event__bar"
                  style={{ background: "var(--color-accent)" }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginBottom: "0.25rem",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.6rem",
                        letterSpacing: "0.1em",
                        color: "var(--color-accent)",
                      }}
                    >
                      {c.ncrp_ref ?? c.id.slice(0, 8)}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.58rem",
                        color: "var(--color-muted-foreground)",
                      }}
                    >
                      {c.state ?? "—"}
                    </span>
                  </div>
                  <p
                    style={{
                      fontSize: "0.76rem",
                      fontWeight: 600,
                      color: "var(--color-foreground)",
                      marginBottom: "0.2rem",
                    }}
                  >
                    {c.fraud_typology ?? "Unclassified"}
                  </p>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.58rem",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {c.amount_lost != null
                      ? `₹${c.amount_lost.toLocaleString("en-IN")}`
                      : "—"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
