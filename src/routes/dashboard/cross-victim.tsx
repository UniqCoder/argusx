import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCorrelation } from "@/hooks/use-correlation";
import { useCaseContext } from "@/store/case-context-store";
import { BackendOfflineBanner } from "@/components/shared/BackendOfflineBanner";
import { truncateAddress } from "@/lib/address";
import type { Chain, Complaint } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/cross-victim")({
  component: CrossVictim,
});

// ── Animated node graph — 3 victims converging on 1 wallet ────────────────
const CV_NODES = [
  { id: "v1", x: 80, y: 60, label: "VICTIM A", type: "victim" },
  { id: "v2", x: 80, y: 180, label: "VICTIM B", type: "victim" },
  { id: "v3", x: 80, y: 300, label: "VICTIM C", type: "victim" },
  { id: "r1", x: 310, y: 180, label: "REPORTED", type: "reported" },
  { id: "e1", x: 510, y: 180, label: "EXCHANGE", type: "exchange" },
];
const CV_EDGES = [
  { from: "v1", to: "r1" },
  { from: "v2", to: "r1" },
  { from: "v3", to: "r1" },
  { from: "r1", to: "e1" },
];
const NODE_C: Record<string, string> = {
  victim: "oklch(0.72 0.024 250)",
  reported: "oklch(0.64 0.22 18)",
  exchange: "oklch(0.79 0.15 74)",
};

// ── Page ─────────────────────────────────────────────────────────────────
function CrossVictim() {
  const navigate = useNavigate();
  const { setActiveWallet, recentWallets } = useCaseContext();

  const [input, setInput] = useState("");
  const [wallet, setWallet] = useState<string | null>(null);
  const [chain, setChain] = useState<
    "BTC" | "ETH" | "TRON" | "BSC" | "Polygon"
  >("ETH");

  const {
    signal: sig,
    linkedComplaints,
    loading,
    error,
  } = useCorrelation(wallet, chain as Chain);

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
    if (!trimmed) return;
    setWallet(trimmed);
  };

  const handlePreset = (addr: string) => {
    setInput(addr);
    setWallet(addr);
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
          style={{ padding: "1rem 1.25rem", display: "flex", gap: "0.5rem" }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Paste wallet — 0x…   T…   1A…   or tx hash"
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
            disabled={!input.trim() || loading}
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
          {recentWallets.length === 0 ? (
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
              {recentWallets.map((addr) => (
                <button
                  key={addr}
                  onClick={() => handlePreset(addr)}
                  style={{
                    padding: "0.28rem 0.65rem",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.6rem",
                    background:
                      wallet === addr
                        ? "oklch(0.83 0.14 205 / 12%)"
                        : "var(--bg-2)",
                    border: `1px solid ${wallet === addr ? "var(--color-accent)" : "var(--border-strong)"}`,
                    borderRadius: "2px",
                    color:
                      wallet === addr
                        ? "var(--color-accent)"
                        : "var(--color-muted-foreground)",
                    cursor: "pointer",
                    letterSpacing: "0.04em",
                    transition: "all 0.12s",
                  }}
                >
                  {truncateAddress(addr)}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Empty state ── */}
      {!wallet && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 360px",
            gap: "0.75rem",
            alignItems: "start",
          }}
        >
          {/* Explainer graph */}
          <div className="ug-surface" style={{ overflow: "hidden" }}>
            <div className="ug-panel-header">
              <span className="ug-section-title" style={{ marginBottom: 0 }}>
                How it works
              </span>
            </div>
            <div style={{ padding: "1.5rem", height: 240 }}>
              <svg
                viewBox="0 0 600 360"
                style={{ width: "100%", height: "100%" }}
              >
                {CV_EDGES.map((e, i) => {
                  const a = CV_NODES.find((n) => n.id === e.from)!;
                  const b = CV_NODES.find((n) => n.id === e.to)!;
                  return (
                    <line
                      key={i}
                      x1={a.x}
                      y1={a.y}
                      x2={b.x}
                      y2={b.y}
                      stroke="oklch(0.83 0.14 205 / 30%)"
                      strokeWidth={1.5}
                      strokeDasharray="4 3"
                    />
                  );
                })}
                {CV_NODES.map((n) => {
                  const col = NODE_C[n.type] ?? "var(--color-muted-foreground)";
                  return (
                    <g key={n.id}>
                      <rect
                        x={n.x - 12}
                        y={n.y - 12}
                        width={24}
                        height={24}
                        transform={`rotate(45,${n.x},${n.y})`}
                        fill={`${col.slice(0, -1)} / 12%)`}
                        stroke={col}
                        strokeWidth={1.5}
                      />
                      <text
                        x={n.x}
                        y={n.y + 30}
                        textAnchor="middle"
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 9,
                          fill: "var(--color-muted-foreground)",
                          letterSpacing: "0.08em",
                        }}
                      >
                        {n.label}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </div>
            <div style={{ padding: "0 1.25rem 1.25rem" }}>
              <p
                style={{
                  fontSize: "0.78rem",
                  color: "var(--color-muted-foreground)",
                  lineHeight: 1.7,
                }}
              >
                Multiple victims independently file complaints — each points to
                the same wallet cluster. Argus links them automatically and
                shows the full picture: how many people were targeted, across
                which states, and how much is at risk.
              </p>
            </div>
          </div>

          {/* Steps */}
          <div className="ug-surface" style={{ overflow: "hidden" }}>
            <div className="ug-panel-header">
              <span className="ug-section-title" style={{ marginBottom: 0 }}>
                What you get
              </span>
            </div>
            <div style={{ padding: "0.75rem 1.25rem 1.25rem" }}>
              {[
                {
                  n: "01",
                  title: "Victim count",
                  body: "Total unique victims linked to the same wallet or cluster.",
                },
                {
                  n: "02",
                  title: "Complaint correlation",
                  body: "Each NCRP complaint matched by wallet address, amounts, and timestamps.",
                },
                {
                  n: "03",
                  title: "Geographic spread",
                  body: "State-by-state breakdown showing scale of the fraud operation.",
                },
                {
                  n: "04",
                  title: "Signal strength",
                  body: "HIGH / MEDIUM / LOW — how confident the correlation is.",
                },
                {
                  n: "05",
                  title: "One-click investigation",
                  body: "Jump straight to the full trace from any linked complaint.",
                },
              ].map(({ n, title, body }) => (
                <div
                  key={n}
                  style={{
                    display: "flex",
                    gap: "0.75rem",
                    paddingBottom: "0.85rem",
                    marginBottom: "0.85rem",
                    borderBottom:
                      n !== "05" ? "1px solid var(--border-subtle)" : "none",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.58rem",
                      color: "var(--color-accent)",
                      flexShrink: 0,
                      letterSpacing: "0.1em",
                      paddingTop: "0.1rem",
                    }}
                  >
                    {n}
                  </span>
                  <div>
                    <p
                      style={{
                        fontSize: "0.76rem",
                        fontWeight: 600,
                        color: "var(--color-foreground)",
                        marginBottom: "0.2rem",
                      }}
                    >
                      {title}
                    </p>
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.62rem",
                        color: "var(--color-muted-foreground)",
                        lineHeight: 1.55,
                      }}
                    >
                      {body}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Loading / offline states (wallet searched, no result yet) ── */}
      {wallet && !sig && (
        <div className="ug-surface" style={{ padding: "1rem 1.25rem", marginBottom: "0.75rem" }}>
          {loading && !error && (
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-muted-foreground)" }}>
              Correlating…
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
                    if (!wallet) return;
                    // A complaint's own id isn't a Case id — only set what's
                    // real: the wallet this correlation was run against.
                    setActiveWallet(wallet, chain);
                    navigate({ to: "/dashboard/investigation" });
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

            {/* ── Right column ── */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "0.75rem",
              }}
            >
              {/* Signal card */}
              <div
                className="ug-surface ug-surface--critical"
                style={{ overflow: "hidden" }}
              >
                <div className="ug-panel-header">
                  <span
                    className="ug-section-title"
                    style={{ marginBottom: 0 }}
                  >
                    Correlation Signal
                  </span>
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.64rem",
                      color: sigColor,
                      fontWeight: 700,
                      letterSpacing: "0.12em",
                    }}
                  >
                    {sig.signalStrength}
                  </span>
                </div>
                <div style={{ padding: "0.75rem 1.25rem 1rem" }}>
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.6rem",
                      color: "var(--color-accent)",
                      marginBottom: "0.75rem",
                      wordBreak: "break-all",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {sig.wallet}
                  </p>
                  {[
                    { k: "Victims", v: String(sig.victims) },
                    { k: "Complaints", v: String(sig.complaints) },
                    { k: "States", v: String(sig.states) },
                    { k: "Funds at Risk", v: sig.totalFundsAtRisk },
                    { k: "Days Active", v: `${daysActive}d` },
                  ].map(({ k, v }) => (
                    <div key={k} className="ug-data-row">
                      <span className="ug-data-row__key">{k}</span>
                      <span
                        className="ug-data-row__value"
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.7rem",
                        }}
                      >
                        {v}
                      </span>
                    </div>
                  ))}

                  {/* Signal strength bar */}
                  <div style={{ marginTop: "0.75rem" }}>
                    <div className="ug-risk-bar">
                      <div
                        className="ug-risk-bar__fill"
                        style={{
                          width:
                            sig.signalStrength === "HIGH"
                              ? "88%"
                              : sig.signalStrength === "MEDIUM"
                                ? "55%"
                                : "25%",
                          background: sigColor,
                        }}
                      />
                    </div>
                  </div>
                </div>
              </div>

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
