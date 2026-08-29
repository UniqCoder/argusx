import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { MOCK_CASES } from "@/lib/mock-data";

export const Route = createFileRoute("/dashboard/deposit")({
  component: DepositWatch,
});

// Chains the user can pick
const CHAINS = ["Ethereum", "Bitcoin", "TRON", "BSC", "Polygon"] as const;
type Chain = (typeof CHAINS)[number];

const CHECK_STEPS = [
  {
    key: "registry",
    label: "Wallet Registry Check",
    detail: "Cross-referencing NCRP complaint database",
  },
  {
    key: "risk",
    label: "Risk Intelligence Score",
    detail: "Running XGBoost risk model on wallet history",
  },
  {
    key: "complaints",
    label: "Complaint Correlation",
    detail: "Matching linked victim complaints",
  },
  {
    key: "signals",
    label: "Network Signal Analysis",
    detail: "Checking cross-chain wallet clustering",
  },
];

type Phase = "idle" | "checking" | "result";

function DepositWatch() {
  const navigate = useNavigate();
  const { setActiveCase } = useCaseContext();

  // User-editable inputs
  const [wallet, setWallet] = useState("0xA7F...82B");
  const [amount, setAmount] = useState("4.82");
  const [chain, setChain] = useState<Chain>("Ethereum");

  // Simulation state
  const [phase, setPhase] = useState<Phase>("idle");
  const [visible, setVisible] = useState<string[]>([]);
  const [action, setAction] = useState<"flagged" | "allowed" | null>(null);

  // Result derived from input (higher amount = higher simulated risk)
  const parsedAmount = parseFloat(amount) || 0;
  const riskScore = Math.min(98, Math.round(60 + parsedAmount * 3));
  const isFlagged = riskScore > 70;
  const scoreColor =
    riskScore > 80
      ? "var(--color-signal)"
      : riskScore > 55
        ? "var(--color-primary)"
        : "var(--color-accent)";

  const simulate = () => {
    if (!wallet.trim()) return;
    setPhase("checking");
    setVisible([]);
    setAction(null);
    CHECK_STEPS.forEach(({ key }, i) => {
      setTimeout(() => setVisible((v) => [...v, key]), 450 + i * 420);
    });
    setTimeout(() => setPhase("result"), 450 + CHECK_STEPS.length * 420 + 300);
  };

  const reset = () => {
    setPhase("idle");
    setVisible([]);
    setAction(null);
  };

  const handleFlagAndInvestigate = () => {
    setAction("flagged");
    // Load the closest matching mock case into context then open investigation
    const matched =
      MOCK_CASES.find(
        (c) => c.blockchain === chain || c.traceStatus === "critical",
      ) ?? MOCK_CASES[0]!;
    setActiveCase({
      caseId: matched.id,
      caseNumber: matched.id,
      wallet: wallet,
      chain: chain as "BTC" | "ETH" | "TRON" | "BSC" | "Polygon",
      fraudType: matched.fraudType,
      status: matched.traceStatus,
    });
  };

  return (
    <>
      {/* Header */}
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Operations</p>
          <h1 className="ug-page-header__title">Deposit Watch</h1>
          <p
            className="ug-page-header__sub"
            style={{ color: "var(--color-primary)" }}
          >
            Stop the money before cash-out — real-time VASP chokepoint check.
          </p>
        </div>
        <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
          <span className="ug-system-live__dot" />
          MONITORING
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
        {/* ── Left column: simulation ── */}
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
        >
          {/* Input card */}
          <div
            className={`ug-surface${phase !== "idle" ? " ug-surface--critical" : ""}`}
            style={{ overflow: "hidden" }}
          >
            <div className="ug-panel-header">
              <div>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.56rem",
                    letterSpacing: "0.3em",
                    textTransform: "uppercase",
                    color:
                      phase === "idle"
                        ? "var(--color-muted-foreground)"
                        : "var(--color-signal)",
                    marginBottom: "0.25rem",
                  }}
                >
                  {phase === "idle"
                    ? "INCOMING DEPOSIT — ENTER DETAILS"
                    : "NEW DEPOSIT DETECTED"}
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.9rem",
                    fontWeight: 700,
                    color: "var(--color-foreground)",
                    letterSpacing: "0.04em",
                  }}
                >
                  {wallet || "—"}
                </p>
              </div>
              <div style={{ textAlign: "right" }}>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.54rem",
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    color: "var(--color-muted-foreground)",
                    marginBottom: "0.2rem",
                  }}
                >
                  Chain
                </p>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.78rem",
                    color: "var(--color-accent)",
                  }}
                >
                  {chain}
                </p>
              </div>
            </div>

            {/* Editable fields — only shown when idle */}
            {phase === "idle" && (
              <div
                style={{
                  padding: "0 1.25rem 1rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
                }}
              >
                {/* Wallet input */}
                <div>
                  <label
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.54rem",
                      letterSpacing: "0.22em",
                      textTransform: "uppercase",
                      color: "var(--color-muted-foreground)",
                      display: "block",
                      marginBottom: "0.4rem",
                    }}
                  >
                    Wallet Address
                  </label>
                  <input
                    value={wallet}
                    onChange={(e) => setWallet(e.target.value)}
                    placeholder="0x…  T…  1A…"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.6rem 0.85rem",
                      background: "var(--bg-2)",
                      border: "1px solid var(--border-strong)",
                      borderRadius: "2px",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.82rem",
                      color: "var(--color-foreground)",
                      outline: "none",
                    }}
                    onFocus={(e) => {
                      e.target.style.borderColor = "var(--color-accent)";
                    }}
                    onBlur={(e) => {
                      e.target.style.borderColor = "var(--border-strong)";
                    }}
                  />
                </div>

                {/* Amount + Chain row */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr",
                    gap: "0.5rem",
                  }}
                >
                  <div>
                    <label
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.54rem",
                        letterSpacing: "0.22em",
                        textTransform: "uppercase",
                        color: "var(--color-muted-foreground)",
                        display: "block",
                        marginBottom: "0.4rem",
                      }}
                    >
                      Amount
                    </label>
                    <input
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                      placeholder="0.00"
                      type="number"
                      min="0"
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        padding: "0.6rem 0.85rem",
                        background: "var(--bg-2)",
                        border: "1px solid var(--border-strong)",
                        borderRadius: "2px",
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.82rem",
                        color: "var(--color-foreground)",
                        outline: "none",
                      }}
                      onFocus={(e) => {
                        e.target.style.borderColor = "var(--color-accent)";
                      }}
                      onBlur={(e) => {
                        e.target.style.borderColor = "var(--border-strong)";
                      }}
                    />
                  </div>
                  <div>
                    <label
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.54rem",
                        letterSpacing: "0.22em",
                        textTransform: "uppercase",
                        color: "var(--color-muted-foreground)",
                        display: "block",
                        marginBottom: "0.4rem",
                      }}
                    >
                      Blockchain
                    </label>
                    <select
                      value={chain}
                      onChange={(e) => setChain(e.target.value as Chain)}
                      style={{
                        width: "100%",
                        boxSizing: "border-box",
                        padding: "0.6rem 0.85rem",
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
                      {CHAINS.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <button
                  className="ug-btn-primary"
                  onClick={simulate}
                  disabled={!wallet.trim()}
                  style={{
                    width: "100%",
                    justifyContent: "center",
                    fontSize: "0.74rem",
                    marginTop: "0.25rem",
                  }}
                >
                  Run Deposit Check
                </button>
              </div>
            )}

            {/* Read-only meta row shown once checking starts */}
            {phase !== "idle" && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(3, 1fr)",
                  borderTop: "1px solid var(--border-strong)",
                }}
              >
                {[
                  {
                    k: "Amount",
                    v: `${amount} ${chain === "Ethereum" ? "ETH" : chain === "Bitcoin" ? "BTC" : chain === "TRON" ? "TRX" : chain === "BSC" ? "BNB" : "MATIC"}`,
                    c: "var(--color-primary)",
                  },
                  {
                    k: "Destination",
                    v: "Exchange Sandbox",
                    c: "var(--color-foreground)",
                  },
                  { k: "Chain", v: chain, c: "var(--color-accent)" },
                ].map(({ k, v, c }, i) => (
                  <div
                    key={k}
                    style={{
                      background: "var(--bg-2)",
                      padding: "0.75rem 1rem",
                      borderRight:
                        i < 2 ? "1px solid var(--border-strong)" : "none",
                    }}
                  >
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.54rem",
                        letterSpacing: "0.2em",
                        textTransform: "uppercase",
                        color: "var(--color-muted-foreground)",
                        marginBottom: "0.25rem",
                      }}
                    >
                      {k}
                    </p>
                    <p
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: "0.78rem",
                        color: c,
                        fontWeight: 600,
                      }}
                    >
                      {v}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Checklist */}
          {phase !== "idle" && (
            <div className="ug-surface" style={{ overflow: "hidden" }}>
              <div className="ug-panel-header">
                <span className="ug-section-title" style={{ marginBottom: 0 }}>
                  Checking Intelligence Registry
                </span>
                {phase === "checking" && (
                  <span
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.56rem",
                      color: "var(--color-accent)",
                      letterSpacing: "0.12em",
                    }}
                  >
                    {visible.length}/{CHECK_STEPS.length} DONE
                  </span>
                )}
              </div>
              <div style={{ padding: "0.5rem 1.25rem 1rem" }}>
                {CHECK_STEPS.map(({ key, label, detail }) => {
                  const done = visible.includes(key);
                  return (
                    <div
                      key={key}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.85rem",
                        padding: "0.6rem 0",
                        borderBottom: "1px solid var(--border-subtle)",
                        opacity: done ? 1 : 0.38,
                        transition: "opacity 0.3s ease",
                      }}
                    >
                      <span
                        style={{
                          width: 18,
                          height: 18,
                          flexShrink: 0,
                          border: `1.5px solid ${done ? "var(--color-accent)" : "var(--border-strong)"}`,
                          borderRadius: "2px",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          color: "var(--color-accent)",
                          fontSize: "0.6rem",
                          background: done
                            ? "oklch(0.83 0.14 205 / 10%)"
                            : "transparent",
                          transition: "all 0.2s",
                        }}
                      >
                        {done ? "✓" : ""}
                      </span>
                      <div style={{ flex: 1 }}>
                        <p
                          style={{
                            fontSize: "0.76rem",
                            color: done
                              ? "var(--color-foreground)"
                              : "var(--color-muted-foreground)",
                            fontWeight: 500,
                            marginBottom: "0.1rem",
                          }}
                        >
                          {label}
                        </p>
                        <p
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.58rem",
                            color: "var(--color-muted-foreground)",
                          }}
                        >
                          {detail}
                        </p>
                      </div>
                      {done && (
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: "0.58rem",
                            color: "var(--color-accent)",
                            letterSpacing: "0.1em",
                            flexShrink: 0,
                          }}
                        >
                          CLEAR
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Risk assessment result */}
          {phase === "result" && !action && (
            <div
              className={`ug-surface${isFlagged ? " ug-surface--critical" : ""}`}
              style={{
                overflow: "hidden",
                animation: "ug-check-in 0.35s ease both",
              }}
            >
              <div className="ug-panel-header">
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.56rem",
                    letterSpacing: "0.3em",
                    textTransform: "uppercase",
                    color: isFlagged
                      ? "var(--color-signal)"
                      : "var(--color-accent)",
                  }}
                >
                  RISK ASSESSMENT COMPLETE
                </span>
                <span
                  className={`ug-badge ${isFlagged ? "ug-badge--critical" : "ug-badge--medium"}`}
                >
                  {isFlagged ? "FLAGGED WALLET" : "LOW RISK"}
                </span>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto 1fr",
                  gap: "1.5rem",
                  padding: "1.25rem",
                  alignItems: "center",
                }}
              >
                <div style={{ textAlign: "center" }}>
                  <p
                    style={{
                      fontSize: "3.5rem",
                      fontWeight: 700,
                      letterSpacing: "-0.06em",
                      color: scoreColor,
                      lineHeight: 1,
                    }}
                  >
                    {riskScore}
                  </p>
                  <p
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.54rem",
                      letterSpacing: "0.14em",
                      color: "var(--color-muted-foreground)",
                    }}
                  >
                    / 100 RISK
                  </p>
                </div>
                <div>
                  {[
                    { k: "Wallet", v: wallet },
                    {
                      k: "Matched Complaints",
                      v: isFlagged ? "4 linked" : "None",
                      c: isFlagged
                        ? "var(--color-signal)"
                        : "var(--color-accent)",
                    },
                    {
                      k: "Network Signal",
                      v: isFlagged ? "HIGH" : "LOW",
                      c: isFlagged
                        ? "var(--color-signal)"
                        : "var(--color-accent)",
                    },
                    {
                      k: "Recommended Action",
                      v: isFlagged ? "Flag for Review" : "Allow",
                      c: isFlagged
                        ? "var(--color-signal)"
                        : "var(--color-accent)",
                    },
                  ].map(({ k, v, c }) => (
                    <div key={k} className="ug-data-row">
                      <span className="ug-data-row__key">{k}</span>
                      <span
                        className="ug-data-row__value"
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: "0.7rem",
                          color: c ?? "var(--color-foreground)",
                          fontWeight: c ? 700 : 400,
                        }}
                      >
                        {v}
                      </span>
                    </div>
                  ))}
                  <div className="ug-risk-bar" style={{ marginTop: "0.75rem" }}>
                    <div
                      className="ug-risk-bar__fill"
                      style={{ width: `${riskScore}%`, background: scoreColor }}
                    />
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  gap: "0.5rem",
                  padding: "0 1.25rem 1.25rem",
                }}
              >
                {isFlagged ? (
                  <>
                    <button
                      className="ug-btn-primary"
                      onClick={handleFlagAndInvestigate}
                      style={{
                        flex: 1,
                        justifyContent: "center",
                        background: "var(--color-signal)",
                        boxShadow: "0 0 24px oklch(0.64 0.22 18 / 30%)",
                      }}
                    >
                      Flag + Open Investigation
                    </button>
                    <button
                      className="ug-btn-ghost"
                      onClick={() => setAction("allowed")}
                      style={{ flexShrink: 0, padding: "0 1rem" }}
                    >
                      Override / Allow
                    </button>
                  </>
                ) : (
                  <button
                    className="ug-btn-primary"
                    onClick={() => setAction("allowed")}
                    style={{ flex: 1, justifyContent: "center" }}
                  >
                    Allow Transaction
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Outcome confirmation */}
          {action && (
            <div
              className="ug-surface"
              style={{
                padding: "1rem 1.25rem",
                borderLeft: `2px solid ${action === "flagged" ? "var(--color-signal)" : "var(--color-accent)"}`,
                animation: "ug-check-in 0.25s ease both",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color:
                    action === "flagged"
                      ? "var(--color-signal)"
                      : "var(--color-accent)",
                  marginBottom: "0.4rem",
                }}
              >
                {action === "flagged"
                  ? "Wallet flagged for review. Case created."
                  : "Transaction allowed. Passive monitoring active."}
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-muted-foreground)",
                  marginBottom: "0.85rem",
                }}
              >
                {action === "flagged"
                  ? `Wallet ${wallet} has been escalated. Freeze request logged for ${chain} chain.`
                  : `Wallet ${wallet} passed the check. Low-priority watch activated.`}
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {action === "flagged" && (
                  <button
                    className="ug-btn-primary"
                    onClick={() => navigate({ to: "/dashboard/investigation" })}
                    style={{ padding: "0.35rem 1rem", fontSize: "0.64rem" }}
                  >
                    Open Investigation
                  </button>
                )}
                <button
                  className="ug-btn-ghost"
                  onClick={reset}
                  style={{ padding: "0.35rem 0.85rem", fontSize: "0.64rem" }}
                >
                  Reset
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ── Right column: API panel ── */}
        <div className="ug-surface" style={{ overflow: "hidden" }}>
          <div className="ug-panel-header">
            <span className="ug-section-title" style={{ marginBottom: 0 }}>
              API Integration
            </span>
            <span
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.54rem",
                color: "var(--color-accent)",
                letterSpacing: "0.08em",
              }}
            >
              REST
            </span>
          </div>

          <div style={{ padding: "1rem" }}>
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-accent)",
                marginBottom: "0.85rem",
                letterSpacing: "0.06em",
              }}
            >
              POST /v1/check-deposit
            </p>

            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.54rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--color-muted-foreground)",
                marginBottom: "0.35rem",
              }}
            >
              Request
            </p>
            <pre
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.65rem",
                color: "var(--color-foreground)",
                background: "var(--bg-2)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "2px",
                padding: "0.75rem",
                marginBottom: "1rem",
                overflow: "auto",
                lineHeight: 1.7,
              }}
            >{`{
  "address": "${wallet || "0x..."}",
  "amount": "${amount || "0"}",
  "chain": "${chain.toLowerCase()}"
}`}</pre>

            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.54rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--color-muted-foreground)",
                marginBottom: "0.35rem",
              }}
            >
              Response
            </p>
            <pre
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.65rem",
                background: "var(--bg-2)",
                border: "1px solid var(--border-subtle)",
                borderLeft: `2px solid ${phase === "result" ? scoreColor : "var(--border-strong)"}`,
                borderRadius: "2px",
                padding: "0.75rem",
                overflow: "auto",
                lineHeight: 1.7,
                color: "var(--color-foreground)",
                transition: "border-color 0.3s",
              }}
            >
              {phase === "result"
                ? `{
  "risk_score": ${riskScore},
  "flagged": ${isFlagged},
  "matched_complaints": ${isFlagged ? 4 : 0},
  "network_signal": "${isFlagged ? "HIGH" : "LOW"}",
  "recommended_action":
    "${isFlagged ? "flag_for_review" : "allow"}",
  "trace_id": "UG-2026-04821"
}`
                : `{
  "risk_score": ...,
  "flagged": ...,
  "matched_complaints": ...,
  "network_signal": "...",
  "recommended_action": "...",
  "trace_id": "..."
}`}
            </pre>

            <div className="ug-divider" />

            {/* What this feature does — plain language */}
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.54rem",
                letterSpacing: "0.22em",
                textTransform: "uppercase",
                color: "var(--color-muted-foreground)",
                margin: "0.75rem 0 0.5rem",
              }}
            >
              What this does
            </p>
            <p
              style={{
                fontSize: "0.72rem",
                color: "var(--color-muted-foreground)",
                lineHeight: 1.7,
                marginBottom: "0.85rem",
              }}
            >
              When a criminal's wallet tries to deposit into a crypto exchange,
              the exchange calls this API{" "}
              <strong style={{ color: "var(--color-foreground)" }}>
                before processing the transaction
              </strong>
              . If the wallet is linked to fraud complaints, Argus returns a
              flag — and the exchange can freeze the deposit before the criminal
              cashes out.
            </p>

            {[
              { icon: "◈", text: "< 200ms latency" },
              { icon: "◈", text: "99.9% uptime SLA" },
              { icon: "◈", text: "FATF-compliant output" },
              { icon: "◈", text: "Webhook alerts" },
            ].map(({ icon, text }) => (
              <div
                key={text}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.55rem",
                  padding: "0.32rem 0",
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.63rem",
                  color: "var(--color-muted-foreground)",
                  borderBottom: "1px solid var(--border-subtle)",
                }}
              >
                <span style={{ color: "var(--color-accent)", flexShrink: 0 }}>
                  {icon}
                </span>
                {text}
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
