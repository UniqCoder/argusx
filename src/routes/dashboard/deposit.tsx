import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { checkDeposit } from "@/lib/api";
import { ApiRequestError } from "@/lib/api";
import type { AlertAction, Chain } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/deposit")({
  component: DepositWatch,
});

const CHAIN_OPTIONS: { label: string; value: Chain }[] = [
  { label: "Ethereum", value: "ETH" },
  { label: "Bitcoin", value: "BTC" },
  { label: "TRON", value: "TRON" },
];

type Phase = "idle" | "checking" | "result" | "error";

function DepositWatch() {
  const navigate = useNavigate();
  const { setActiveWallet } = useCaseContext();

  const [wallet, setWallet] = useState("");
  const [amount, setAmount] = useState("1.0");
  const [chain, setChain] = useState<Chain>("ETH");

  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<{
    riskScore: number;
    action: AlertAction;
    caseRef: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<"flagged" | "allowed" | null>(null);

  const run = async () => {
    if (!wallet.trim()) return;
    const parsedAmount = parseFloat(amount);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) return;
    setPhase("checking");
    setResult(null);
    setError(null);
    setOutcome(null);
    try {
      const res = await checkDeposit({
        address: wallet.trim(),
        chain,
        amount: parsedAmount,
      });
      setResult({
        riskScore: Math.round(res.risk_score * 100),
        action: res.action,
        caseRef: res.case_ref ?? null,
      });
      setPhase("result");
    } catch (e) {
      const message =
        e instanceof ApiRequestError
          ? e.message
          : e instanceof Error
            ? e.message
            : "Deposit check failed";
      setError(message);
      setPhase("error");
    }
  };

  const reset = () => {
    setPhase("idle");
    setResult(null);
    setError(null);
    setOutcome(null);
  };

  const isFlagged = result ? result.action !== "allow" : false;
  const scoreColor = !result
    ? "var(--color-accent)"
    : result.action === "block"
      ? "var(--color-signal)"
      : result.action === "hold"
        ? "var(--color-primary)"
        : "var(--color-accent)";

  const handleFlagAndInvestigate = () => {
    setOutcome("flagged");
    setActiveWallet(wallet.trim(), chain);
  };

  return (
    <>
      <div className="ug-page-header">
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Operations</p>
          <h1 className="ug-page-header__title">Deposit Watch</h1>
          <p
            className="ug-page-header__sub"
            style={{ color: "var(--color-primary)" }}
          >
            Check a wallet against the real-time VASP risk registry before
            crediting a deposit.
          </p>
        </div>
        <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
          <span className="ug-system-live__dot" />
          MONITORING
        </div>
      </div>

      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
        >
          {/* Input card */}
          <div
            className={`ug-surface${phase !== "idle" ? " ug-surface--critical" : ""}`}
            style={{ overflow: "hidden" }}
          >
            <div className="ug-panel-header">
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.56rem",
                  letterSpacing: "0.3em",
                  textTransform: "uppercase",
                  color: "var(--color-muted-foreground)",
                }}
              >
                INCOMING DEPOSIT — ENTER DETAILS
              </span>
            </div>

            {phase === "idle" && (
              <div
                style={{
                  padding: "0 1.25rem 1rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.75rem",
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
                  />
                </div>

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
                      step="any"
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
                      {CHAIN_OPTIONS.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <button
                  className="ug-btn-primary"
                  onClick={run}
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

            {phase === "checking" && (
              <div style={{ padding: "1.25rem" }}>
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.68rem",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  Querying risk registry…
                </p>
              </div>
            )}
          </div>

          {phase === "error" && (
            <div
              className="ug-surface"
              style={{
                padding: "1rem 1.25rem",
                borderLeft: "2px solid var(--color-signal)",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color: "var(--color-signal)",
                  marginBottom: "0.4rem",
                }}
              >
                Deposit check failed
              </p>
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.64rem",
                  color: "var(--color-muted-foreground)",
                  marginBottom: "0.85rem",
                }}
              >
                {error}
              </p>
              <button
                className="ug-btn-ghost"
                onClick={reset}
                style={{ padding: "0.35rem 0.85rem", fontSize: "0.64rem" }}
              >
                Try Again
              </button>
            </div>
          )}

          {phase === "result" && result && !outcome && (
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
                  RISK REGISTRY RESULT
                </span>
                <span
                  className={`ug-badge ${isFlagged ? "ug-badge--critical" : "ug-badge--medium"}`}
                >
                  {result.action.toUpperCase()}
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
                    {result.riskScore}
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
                    { k: "Chain", v: chain },
                    {
                      k: "Linked Case",
                      v: result.caseRef ?? "None on file",
                    },
                    {
                      k: "Recommended Action",
                      v:
                        result.action === "block"
                          ? "Block deposit"
                          : result.action === "hold"
                            ? "Hold for review"
                            : "Allow",
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
                      style={{
                        width: `${result.riskScore}%`,
                        background: scoreColor,
                      }}
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
                      onClick={() => setOutcome("allowed")}
                      style={{ flexShrink: 0, padding: "0 1rem" }}
                    >
                      Override / Allow
                    </button>
                  </>
                ) : (
                  <button
                    className="ug-btn-primary"
                    onClick={() => setOutcome("allowed")}
                    style={{ flex: 1, justifyContent: "center" }}
                  >
                    Allow Transaction
                  </button>
                )}
              </div>
            </div>
          )}

          {outcome && (
            <div
              className="ug-surface"
              style={{
                padding: "1rem 1.25rem",
                borderLeft: `2px solid ${outcome === "flagged" ? "var(--color-signal)" : "var(--color-accent)"}`,
                animation: "ug-check-in 0.25s ease both",
              }}
            >
              <p
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.72rem",
                  fontWeight: 700,
                  color:
                    outcome === "flagged"
                      ? "var(--color-signal)"
                      : "var(--color-accent)",
                  marginBottom: "0.4rem",
                }}
              >
                {outcome === "flagged"
                  ? "Wallet flagged. Set as active wallet for investigation."
                  : "Deposit allowed."}
              </p>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {outcome === "flagged" && (
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
      </div>
    </>
  );
}
