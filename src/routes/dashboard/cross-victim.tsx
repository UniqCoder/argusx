import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCorrelation } from "@/hooks/use-correlation";
import { useCaseContext } from "@/store/case-context-store";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import { truncateAddress, isValidTraceInputFor } from "@/lib/address";
import type { Chain, Complaint } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/cross-victim")({
  component: CrossVictim,
});

// ── Page ─────────────────────────────────────────────────────────────────
function CrossVictim() {
  const navigate = useNavigate();
  const { setActiveWallet, recentWallets, recordRecentWallet } =
    useCaseContext();

  const [input, setInput] = useState("");
  const [wallet, setWallet] = useState<string | null>(null);
  const [chain, setChain] = useState<"BTC" | "ETH" | "TRON">("ETH");
  // Bumped on every CORRELATE press so a second press on the SAME wallet
  // fires a new request instead of silently doing nothing — pressing the
  // button used to only call setWallet(trimmed), and React bails on an
  // effect dependency that has not changed.
  const [requestNonce, setRequestNonce] = useState(0);

  const trimmedInput = input.trim();
  const inputValid =
    !trimmedInput || isValidTraceInputFor(chain, trimmedInput);

  const {
    signal: sig,
    linkedComplaints,
    loading,
    error,
    notFound,
  } = useCorrelation(wallet, chain as Chain, requestNonce);

  // Real, derived from actual complaint filing dates — not a fabricated
  // constant. Falls back to 0 when there's nothing to derive it from yet.
  const daysActive = (() => {
    if (linkedComplaints.length === 0) return 0;
    const earliest = Math.min(
      ...linkedComplaints.map((c) => new Date(c.filed_at).getTime()),
    );
    return Math.max(0, Math.round((Date.now() - earliest) / 86_400_000));
  })();

  const handleSearch = () => {
    const trimmed = input.trim();
    if (!trimmed || !isValidTraceInputFor(chain, trimmed)) return;
    setWallet(trimmed);
    setRequestNonce((n) => n + 1);
    recordRecentWallet(trimmed, chain);
  };

  // Restores the wallet AND the chain it was originally searched on, so a
  // preset chip can never pair an address with the wrong chain (the
  // chain-mismatch bug that sent ETH addresses to the BTC explorer).
  const handlePreset = (addr: string, presetChain: typeof chain) => {
    setInput(addr);
    setWallet(addr);
    setChain(presetChain);
    setRequestNonce((n) => n + 1);
  };

  const handleOpenInvestigation = () => {
    if (wallet) setActiveWallet(wallet, chain);
    navigate({ to: "/dashboard/investigation" });
  };

  const sigColor =
    sig?.signalStrength === "HIGH"
      ? "var(--color-signal)"
      : sig?.signalStrength === "MEDIUM"
        ? "var(--color-primary)"
        : "var(--color-accent)";

  return (
    <>
      {/* ── Header ── */}
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Intelligence</p>
          <h1 className="ug-page-header__title">Cross-Victim Correlation</h1>
          <p className="ug-page-header__sub">
            {sig
              ? `${sig.victims} victims · ${sig.complaints} complaints · ${sig.states} states — signal: ${sig.signalStrength}`
              : wallet && loading
                ? "Correlating…"
                : wallet && error
                  ? "Couldn't reach the backend — see below."
                  : "One wallet. Many targets. Paste an address to surface every linked victim."}
          </p>
        </div>
        {sig && (
          <span
            className="ug-badge ug-badge--critical"
            style={{
              fontSize: "0.62rem",
              padding: "0.3rem 0.75rem",
              color: sigColor,
              borderColor: sigColor,
            }}
          >
            SIGNAL: {sig.signalStrength}
          </span>
        )}
      </div>

      {/* ── Search bar ── */}
      <div
        className="ug-surface"
        style={{ overflow: "hidden", marginBottom: "0.75rem" }}
      >
        <div className="ug-panel-header">
          <span className="ug-section-title" style={{ marginBottom: 0 }}>
            Wallet Search
          </span>
          {loading && (
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                color: "var(--color-accent)",
                letterSpacing: "0.14em",
              }}
            >
              CORRELATING…
            </span>
          )}
        </div>

        <div
          style={{
            padding: "1rem 1.25rem",
            display: "flex",
            gap: "0.5rem",
            alignItems: "stretch",
          }}
        >
          {/* The chain the pasted address belongs to — recorded with the
              wallet in the recent list and used for the correlation call.
              Without it, every address searched here was assumed ETH (the
              chain-mismatch bug: a TRON/BTC address then got fetched with
              the wrong explorer and failed). */}
          <select
            value={chain}
            onChange={(e) => setChain(e.target.value as typeof chain)}
            style={{
              padding: "0.75rem 0.85rem",
              background: "var(--bg-2)",
              border: "1px solid var(--border-strong)",
              borderRadius: "2px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.78rem",
              color: "var(--color-foreground)",
              outline: "none",
              cursor: "pointer",
            }}
          >
            <option value="BTC">BTC</option>
            <option value="ETH">ETH</option>
            <option value="TRON">TRX (TRON)</option>
          </select>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Paste wallet — 0x…   T…   1A…"
            style={{
              flex: 1,
              padding: "0.75rem 1rem",
              background: "var(--bg-2)",
              border: "1px solid var(--border-strong)",
              borderRadius: "2px",
              fontFamily: "var(--font-mono)",
              fontSize: "0.88rem",
              color: "var(--color-foreground)",
              outline: "none",
              letterSpacing: "0.04em",
              boxSizing: "border-box",
            }}
            onFocus={(e) => {
              e.target.style.borderColor = "var(--color-accent)";
              e.target.style.boxShadow = "0 0 0 2px oklch(0.83 0.14 205 / 10%)";
            }}
            onBlur={(e) => {
              e.target.style.borderColor = "var(--border-strong)";
              e.target.style.boxShadow = "none";
            }}
          />
          <button
            className="ug-btn-primary"
            onClick={handleSearch}
            disabled={!trimmedInput || !inputValid || loading}
            style={{
              padding: "0.75rem 1.5rem",
              fontSize: "0.72rem",
              whiteSpace: "nowrap",
            }}
          >
            {loading ? "Correlating…" : "CORRELATE →"}
          </button>
        </div>

        {/* Known flagged wallet presets */}
        <div
          style={{
            borderTop: "1px solid var(--border-subtle)",
            padding: "0.6rem 1.25rem 0.9rem",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.54rem",
              letterSpacing: "0.24em",
              textTransform: "uppercase",
              color: "var(--color-muted-foreground)",
              marginBottom: "0.5rem",
            }}
          >
            Recently searched
          </p>
          {(() => {
            const correlatable = recentWallets.filter(
              (e): e is typeof e & { chain: "BTC" | "ETH" | "TRON" } =>
                e.chain === "BTC" || e.chain === "ETH" || e.chain === "TRON",
            );
            return correlatable.length === 0 ? (
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                No wallets searched yet this session.
              </p>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                {correlatable.map((entry) => (
                  <button
                    key={`${entry.chain}:${entry.address}`}
                    onClick={() => handlePreset(entry.address, entry.chain)}
                    style={{
                      padding: "0.28rem 0.65rem",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      background:
                        wallet === entry.address && chain === entry.chain
                          ? "oklch(0.83 0.14 205 / 12%)"
                          : "var(--bg-2)",
                      border: `1px solid ${wallet === entry.address && chain === entry.chain ? "var(--color-accent)" : "var(--border-strong)"}`,
                      borderRadius: "2px",
                      color:
                        wallet === entry.address && chain === entry.chain
                          ? "var(--color-accent)"
                          : "var(--color-muted-foreground)",
                      cursor: "pointer",
                      letterSpacing: "0.04em",
                      transition: "all 0.12s",
                    }}
                  >
                    {truncateAddress(entry.address)}
                  </button>
                ))}
              </div>
            );
          })()}
        </div>
      </div>

      {/* ── Empty state ── */}
      {!wallet && (
        <div
          className="ug-surface"
          style={{
            padding: "2rem 1.25rem",
            textAlign: "center",
            color: "var(--color-muted-foreground)",
          }}
        >
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.62rem",
              letterSpacing: "0.2em",
              textTransform: "uppercase",
            }}
          >
            No wallet searched
          </p>
          <p style={{ fontSize: "0.76rem", marginTop: "0.4rem" }}>
            Paste an address above to correlate it against filed complaints.
          </p>
        </div>
      )}

      {/* ── Loading / offline / not-found states (wallet searched, no signal yet) ── */}
      {wallet && !sig && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "0.75rem" }}>
          {loading && !error && !notFound && (
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
              Correlating…
            </p>
          )}
          {/* A wallet the system has never seen is a real, honest outcome —
              not a backend failure. Previously this fell through to a flash
              of empty bordered surface with no explanation on the first
              render tick before the 404 was even reflected. */}
          {notFound && !loading && (
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.68rem", color: "var(--color-muted-foreground)", lineHeight: 1.7 }}>
              No complaints reference this wallet. It may be uninvolved, or
              simply not yet reported — a correlation signal only exists once
              at least one complaint names the address.
            </p>
          )}
          <BackendOfflineBanner error={error} context="cross-victim correlation" />
        </div>
      )}

      {/* ── Results ── */}
      {wallet && sig && (
        <>
          {/* Summary stat strip */}
          <div className="ug-stat-strip" style={{ marginBottom: "0.75rem" }}>
            {[
              {
                label: "Linked Victims",
                value: sig.victims,
                accent: "var(--color-signal)",
              },
              {
                label: "Complaints Filed",
                value: sig.complaints,
                accent: "var(--color-primary)",
              },
              {
                label: "States Affected",
                value: sig.states,
                accent: "var(--color-accent)",
              },
              {
                label: "Funds at Risk",
                value: sig.totalFundsAtRisk,
                accent: "var(--color-foreground)",
              },
              {
                label: "Days Active",
                value: `${daysActive}d`,
                accent: "var(--color-muted-foreground)",
              },
            ].map((s) => (
              <div
                key={s.label}
                className="ug-stat-cell"
                style={{ borderTop: `2px solid ${s.accent}` }}
              >
                <span
                  className="ug-stat-cell__value"
                  style={{ color: s.accent }}
                >
                  {s.value}
                </span>
                <span className="ug-stat-cell__label">{s.label}</span>
              </div>
            ))}
          </div>

          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 296px",
              gap: "0.75rem",
              alignItems: "start",
            }}
          >
            {/* ── Left: linked complaints table ── */}
            <div className="ug-surface" style={{ overflow: "hidden" }}>
              <div className="ug-panel-header">
                <span className="ug-section-title" style={{ marginBottom: 0 }}>
                  Linked Complaints
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.58rem",
                      color: "var(--color-muted-foreground)",
                      marginLeft: "0.5rem",
                      fontWeight: 400,
                    }}
                  >
                    {sig.complaints} matched
                  </span>
                </span>
                <button
                  className="ug-btn-primary"
                  onClick={handleOpenInvestigation}
                  style={{ padding: "0.32rem 0.8rem", fontSize: "0.6rem" }}
                >
                  Open Investigation →
                </button>
              </div>

              {/* Table head */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "88px 1fr 90px 100px 100px",
                  padding: "0.45rem 1.25rem",
                  borderBottom: "1px solid var(--border-strong)",
                  background: "var(--bg-2)",
                }}
              >
                {[
                  "Case ID",
                  "Fraud / Description",
                  "Amount",
                  "State",
                  "Status",
                ].map((h) => (
                  <span
                    key={h}
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.52rem",
                      letterSpacing: "0.2em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {h}
                  </span>
                ))}
              </div>

              {/* Rows */}
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
              {linkedComplaints.map((c: Complaint, i) => (
                <div
                  key={c.id}
                  onClick={() => {
                    if (wallet) setActiveWallet(wallet, chain);
                    navigate({
                      to: "/dashboard/complaints/$id",
                      params: { id: c.id },
                    });
                  }}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "88px 1fr 90px 100px 100px",
                    padding: "0.7rem 1.25rem",
                    borderBottom:
                      i < linkedComplaints.length - 1
                        ? "1px solid var(--border-subtle)"
                        : "none",
                    alignItems: "center",
                    cursor: "pointer",
                    transition: "background 0.12s",
                  }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = "oklch(0.98 0 0 / 2%)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "transparent")
                  }
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      color: "var(--color-accent)",
                    }}
                  >
                    {(c.ncrp_ref ?? c.id).slice(-5)}
                  </span>
                  <div>
                    <p
                      style={{
                        fontSize: "0.74rem",
                        fontWeight: 600,
                        color: "var(--color-foreground)",
                        marginBottom: "0.15rem",
                      }}
                    >
                      {c.fraud_typology ?? "Unclassified"}
                    </p>
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.58rem",
                        color: "var(--color-muted-foreground)",
                      }}
                    >
                      {(c.narrative_text ?? "No narrative on file").length > 52
                        ? (c.narrative_text ?? "").slice(0, 52) + "…"
                        : (c.narrative_text ?? "No narrative on file")}
                    </p>
                  </div>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.64rem",
                      color: "var(--color-primary)",
                    }}
                  >
                    {c.amount_lost != null
                      ? `₹${c.amount_lost.toLocaleString("en-IN")}`
                      : "—"}
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.62rem",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    {c.state ?? "—"}
                  </span>
                  <span
                    className="ug-badge ug-badge--medium"
                    style={{ fontSize: "0.5rem", justifySelf: "start" }}
                  >
                    {c.source_platform}
                  </span>
                </div>
              ))}
            </div>

            {/* ── Right column: Intelligence panel ── */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              {(() => {
                const geoStates = Array.from(
                  new Set(
                    linkedComplaints
                      .map((c) => c.state)
                      .filter((s): s is string => !!s),
                  ),
                );

                const rows: { n: string; label: string; body: React.ReactNode }[] = [
                  {
                    n: "01",
                    label: "Victim Count",
                    body:
                      sig.victims > 0 ? (
                        `${sig.victims} linked victim${sig.victims === 1 ? "" : "s"}`
                      ) : (
                        <em>NO MATCHES</em>
                      ),
                  },
                  {
                    n: "02",
                    label: "Complaint Correlation",
                    body:
                      sig.complaints > 0 ? (
                        <>
                          {sig.complaints} matching complaint
                          {sig.complaints === 1 ? "" : "s"}
                          <br />
                          <span style={{ opacity: 0.7 }}>
                            Address · amount · timestamp
                          </span>
                        </>
                      ) : (
                        <em>NO MATCHES — no correlated complaints found</em>
                      ),
                  },
                  {
                    n: "03",
                    label: "Geographic Spread",
                    body:
                      geoStates.length > 0 ? (
                        geoStates.join(" · ")
                      ) : (
                        <em>NOT ATTRIBUTED — no state on file</em>
                      ),
                  },
                  {
                    n: "04",
                    label: "Signal Strength",
                    body: (
                      <span style={{ color: sigColor, fontWeight: 700 }}>
                        {sig.signalStrength}
                      </span>
                    ),
                  },
                  {
                    n: "05",
                    label: "Investigation",
                    body: (
                      <button
                        onClick={handleOpenInvestigation}
                        style={{
                          background: "none",
                          border: "none",
                          padding: 0,
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.68rem",
                          color: "var(--color-accent)",
                          cursor: "pointer",
                        }}
                      >
                        View linked evidence →
                      </button>
                    ),
                  },
                ];

                return (
                  <div
                    className="ug-surface ug-surface--critical"
                    style={{ overflow: "hidden" }}
                  >
                    <div className="ug-panel-header">
                      <span
                        className="ug-section-title"
                        style={{ marginBottom: 0 }}
                      >
                        Intelligence
                      </span>
                    </div>
                    <div style={{ padding: "0.4rem 1.25rem 0.4rem" }}>
                      <p
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.6rem",
                          color: "var(--color-accent)",
                          margin: "0.5rem 0 0.75rem",
                          wordBreak: "break-all",
                          letterSpacing: "0.04em",
                        }}
                      >
                        {sig.wallet}
                      </p>
                      {rows.map(({ n, label, body }, i) => (
                        <div
                          key={n}
                          style={{
                            display: "flex",
                            gap: "0.65rem",
                            padding: "0.65rem 0",
                            borderTop:
                              i === 0 ? "none" : "1px solid var(--border-subtle)",
                          }}
                        >
                          <span
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: "0.58rem",
                              color: "var(--color-muted-foreground)",
                              flexShrink: 0,
                              letterSpacing: "0.1em",
                              paddingTop: "0.1rem",
                            }}
                          >
                            {n}
                          </span>
                          <div style={{ minWidth: 0 }}>
                            <p
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: "0.54rem",
                                letterSpacing: "0.18em",
                                textTransform: "uppercase",
                                color: "var(--color-muted-foreground)",
                                marginBottom: "0.25rem",
                              }}
                            >
                              {label}
                            </p>
                            <div
                              style={{
                                fontSize: "0.76rem",
                                color: "var(--color-foreground)",
                                lineHeight: 1.5,
                              }}
                            >
                              {body}
                            </div>
                          </div>
                        </div>
                      ))}

                      <div
                        style={{
                          marginTop: "0.5rem",
                          paddingTop: "0.65rem",
                          borderTop: "1px solid var(--border-subtle)",
                        }}
                      >
                        <div className="ug-data-row">
                          <span className="ug-data-row__key">Funds at Risk</span>
                          <span
                            className="ug-data-row__value"
                            style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}
                          >
                            {sig.totalFundsAtRisk}
                          </span>
                        </div>
                        <div className="ug-data-row">
                          <span className="ug-data-row__key">Days Active</span>
                          <span
                            className="ug-data-row__value"
                            style={{ fontFamily: "var(--font-mono)", fontSize: "0.7rem" }}
                          >
                            {daysActive}d
                          </span>
                        </div>
                        <div className="ug-risk-bar" style={{ marginTop: "0.6rem" }}>
                          <div
                            className="ug-risk-bar__fill"
                            style={{
                              width: `${Math.round(sig.correlationScore * 100)}%`,
                              background: sigColor,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                );
              })()}

              {/* Backend offline notice */}
              {error && (
                <div
                  style={{
                    padding: "0.6rem 0.85rem",
                    background: "oklch(0.64 0.22 18 / 8%)",
                    border: "1px solid oklch(0.64 0.22 18 / 30%)",
                    borderRadius: "2px",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.58rem",
                    color: "var(--color-signal)",
                    lineHeight: 1.6,
                  }}
                >
                  Couldn't reach the backend — {error}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </>
  );
}
