import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { formatRiskScore, riskTierColor } from "@/hooks/use-wallet";
import { checkDeposit, recordDepositDecision } from "@/lib/api";
import { ApiRequestError } from "@/lib/api";
import { isValidTraceInputFor } from "@/lib/address";
import { useHealth } from "@/hooks/use-health";
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
  const { setActiveWallet, activeCaseId } = useCaseContext();
  const { isLive } = useHealth();

  const [wallet, setWallet] = useState("");
  const [amount, setAmount] = useState("1.0");
  const [chain, setChain] = useState<Chain>("ETH");
  const [touched, setTouched] = useState(false);

  const [phase, setPhase] = useState<Phase>("idle");
  const [result, setResult] = useState<{
    riskScore: number | null;
    /** The exact 0-1 value the API returned, for anything that WRITES the
     * score (the audit ledger) — `riskScore` above is rounded for display
     * only. Re-deriving a value to persist from an already-rounded display
     * number (`riskScore / 100`) used to bake a coarser number permanently
     * into the compliance ledger than any other surface stores. */
    riskScoreRaw: number | null;
    action: AlertAction;
    caseRef: string | null;
    reason: string | null;
    riskTier: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [outcome, setOutcome] = useState<"flagged" | "allowed" | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);

  const trimmedWallet = wallet.trim();
  const parsedAmount = parseFloat(amount);
  const addressValid = !trimmedWallet || isValidTraceInputFor(chain, trimmedWallet);
  const amountValid = Number.isFinite(parsedAmount) && parsedAmount > 0;
  // The button used to be enabled on address alone, so a cleared or zeroed
  // amount field looked clickable and silently did nothing. Every reason a
  // click would be refused is now visible before the click, not discovered by
  // its absence of effect.
  const canRun = !!trimmedWallet && addressValid && amountValid;

  const run = async () => {
    setTouched(true);
    if (!canRun) return;
    setPhase("checking");
    setError(null);
    setOutcome(null);
    setRecordError(null);
    try {
      const res = await checkDeposit({
        address: trimmedWallet,
        chain,
        amount: parsedAmount,
      });
      // A backend that cannot score a wallet says so honestly (risk_score can
      // be absent) — this used to coerce that into a confident-looking "0",
      // which reads as "checked and clean" rather than "not checked".
      setResult({
        riskScore:
          res.risk_score === null || res.risk_score === undefined
            ? null
            : Math.round(res.risk_score * 100 * 100) / 100,
        riskScoreRaw:
          res.risk_score === null || res.risk_score === undefined
            ? null
            : res.risk_score,
        action: res.action,
        caseRef: res.case_ref ?? null,
        reason: res.reason ?? null,
        riskTier: res.risk_tier ?? null,
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
    setRecordError(null);
    setTouched(false);
  };

  const isFlagged = result ? result.action !== "allow" : false;
  // Color comes from the backend's own risk_tier — the same value Risk
  // Intelligence colors off — not re-derived from `action` (block/hold/
  // allow), which is a decision, not a tier, and doesn't distinguish "never
  // scored, defaults to allow" from "scored, confirmed low risk". A wallet
  // with no registry entry now correctly reads as unscored-gray rather than
  // the same confident cyan as a wallet the model actually cleared.
  const scoreColor = !result ? "var(--color-accent)" : riskTierColor(result.riskTier);

  // Both actions now WRITE the decision server-side before changing local
  // state, so a compliance override is an auditable act with an actor and a
  // timestamp — not a click that only ever existed in this component.
  const recordAndSetOutcome = async (decision: "allowed" | "flagged") => {
    if (!result) return;
    setRecording(true);
    setRecordError(null);
    try {
      await recordDepositDecision({
        address: trimmedWallet,
        chain,
        risk_score: result.riskScoreRaw ?? 0,
        action: result.action,
        decision,
        case_ref: result.caseRef,
        // Real case linkage when the investigator has one open — without
        // this the ledger write still succeeds, but the entry is
        // permanently invisible in any case's Evidence Trail.
        case_id: activeCaseId,
      });
      setOutcome(decision);
      if (decision === "flagged") setActiveWallet(trimmedWallet, chain);
    } catch (e) {
      setRecordError(
        e instanceof Error ? e.message : "Could not record this decision",
      );
    } finally {
      setRecording(false);
    }
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
            Before an exchange credits an incoming deposit, check whether the
            money is traceable to a reported fraud.
          </p>
        </div>
        {/* Wired to the real backend health poll — this used to be a static
            dot that said "MONITORING" regardless of whether anything was
            actually live, next to copy that called the check "real-time
            monitoring" when it is a point-in-time lookup on request. */}
        <div className="ug-system-live" style={{ fontSize: "0.58rem" }}>
          <span
            className="ug-system-live__dot"
            style={{ background: isLive ? undefined : "var(--color-signal)" }}
          />
          {isLive ? "REGISTRY LIVE" : "REGISTRY UNREACHABLE"}
        </div>
      </div>

      <div style={{ maxWidth: 680, margin: "0 auto" }}>
        {/* Three-step framing, always visible, so the page never becomes a
            header with an empty body mid-check. */}
        <div
          style={{
            display: "flex",
            gap: "0.4rem",
            marginBottom: "0.85rem",
            fontFamily: "var(--font-mono)",
            fontSize: "0.58rem",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
          }}
        >
          {(["1 · Incoming deposit", "2 · Check", "3 · Verdict"] as const).map(
            (label, i) => {
              const active =
                (i === 0 && phase === "idle") ||
                (i === 1 && phase === "checking") ||
                (i === 2 && (phase === "result" || phase === "error"));
              return (
                <span
                  key={label}
                  style={{
                    padding: "0.3rem 0.6rem",
                    borderRadius: 2,
                    border: `1px solid ${active ? "var(--color-accent)" : "var(--border-strong)"}`,
                    color: active ? "var(--color-accent)" : "var(--color-muted-foreground)",
                  }}
                >
                  {label}
                </span>
              );
            },
          )}
        </div>

        <div
          style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}
        >
          {/* Input card — stays on screen through every phase, so correcting
              a typo never requires a full Reset. Previously this whole block
              was gated on phase === "idle" and the "result" phase rendered a
              header with no body at all. */}
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
                INCOMING DEPOSIT
              </span>
              {phase !== "idle" && (
                <button
                  className="ug-btn-ghost"
                  onClick={reset}
                  style={{ padding: "0.2rem 0.6rem", fontSize: "0.58rem" }}
                >
                  Edit
                </button>
              )}
            </div>

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
                  onChange={(e) => {
                    setWallet(e.target.value);
                    if (phase !== "idle") setPhase("idle");
                  }}
                  onBlur={() => setTouched(true)}
                  disabled={phase === "checking"}
                  placeholder="0x…  T…  1A…"
                  style={{
                    width: "100%",
                    boxSizing: "border-box",
                    padding: "0.6rem 0.85rem",
                    background: "var(--bg-2)",
                    border: `1px solid ${touched && trimmedWallet && !addressValid ? "var(--color-signal)" : "var(--border-strong)"}`,
                    borderRadius: "2px",
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.82rem",
                    color: "var(--color-foreground)",
                    outline: "none",
                  }}
                />
                {touched && trimmedWallet && !addressValid && (
                  <p style={{ fontSize: "0.62rem", color: "var(--color-signal)", marginTop: "0.3rem" }}>
                    Doesn't look like a {chain} address.
                  </p>
                )}
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
                    onChange={(e) => {
                      setAmount(e.target.value);
                      if (phase !== "idle") setPhase("idle");
                    }}
                    onBlur={() => setTouched(true)}
                    disabled={phase === "checking"}
                    placeholder="0.00"
                    type="number"
                    min="0"
                    step="any"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.6rem 0.85rem",
                      background: "var(--bg-2)",
                      border: `1px solid ${touched && !amountValid ? "var(--color-signal)" : "var(--border-strong)"}`,
                      borderRadius: "2px",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.82rem",
                      color: "var(--color-foreground)",
                      outline: "none",
                    }}
                  />
                  {touched && !amountValid && (
                    <p style={{ fontSize: "0.62rem", color: "var(--color-signal)", marginTop: "0.3rem" }}>
                      Enter an amount greater than zero.
                    </p>
                  )}
                  {/* Honest about what this field does: the backend records it
                      on the alert for the audit trail, but ALLOW/HOLD/BLOCK is
                      decided from the wallet's registry risk tier alone — a
                      $1 and a $10,000,000 deposit to the same flagged address
                      get the same verdict. This used to look like a
                      risk-weighted amount check with no such logic behind it. */}
                  <p
                    style={{
                      fontSize: "0.58rem",
                      color: "var(--color-muted-foreground)",
                      marginTop: "0.3rem",
                      lineHeight: 1.5,
                    }}
                  >
                    Recorded on the alert for the audit trail — the verdict is
                    decided by the wallet's registry risk alone, not the
                    amount.
                  </p>
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
                    onChange={(e) => {
                      setChain(e.target.value as Chain);
                      if (phase !== "idle") setPhase("idle");
                    }}
                    disabled={phase === "checking"}
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

              {phase === "idle" && (
                <button
                  className="ug-btn-primary"
                  onClick={run}
                  style={{
                    width: "100%",
                    justifyContent: "center",
                    fontSize: "0.74rem",
                    marginTop: "0.25rem",
                    opacity: canRun ? 1 : 0.55,
                  }}
                >
                  Run Deposit Check
                </button>
              )}

              {phase === "checking" && (
                <p
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: "0.68rem",
                    color: "var(--color-muted-foreground)",
                  }}
                >
                  Querying risk registry…
                </p>
              )}
            </div>
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
                }}
              >
                {error}
              </p>
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
                  VERDICT
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
                      fontSize: result.riskScore === null ? "1.1rem" : "3.5rem",
                      fontWeight: 700,
                      letterSpacing: "-0.06em",
                      color: result.riskScore === null ? "var(--color-muted-foreground)" : scoreColor,
                      lineHeight: 1,
                    }}
                  >
                    {result.riskScore === null
                      ? "Not scored"
                      : formatRiskScore(result.riskScore)}
                  </p>
                  {result.riskScore !== null && (
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
                  )}
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
                  {result.riskScore !== null && (
                    <div className="ug-risk-bar" style={{ marginTop: "0.75rem" }}>
                      <div
                        className="ug-risk-bar__fill"
                        style={{
                          width: `${result.riskScore}%`,
                          background: scoreColor,
                        }}
                      />
                    </div>
                  )}
                </div>
              </div>

              {/* Why. A bare number was the single biggest complaint about
                  this screen; this is what the registry entry recorded. */}
              {result.reason && (
                <p
                  style={{
                    margin: "0 1.25rem 1rem",
                    padding: "0.6rem 0.75rem",
                    background: "oklch(0.98 0 0 / 3%)",
                    borderLeft: `2px solid ${scoreColor}`,
                    borderRadius: 2,
                    fontSize: "0.7rem",
                    color: "var(--color-muted-foreground)",
                    lineHeight: 1.6,
                  }}
                >
                  {result.reason}
                </p>
              )}

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
                      onClick={() => recordAndSetOutcome("flagged")}
                      disabled={recording}
                      style={{
                        flex: 1,
                        justifyContent: "center",
                        background: "var(--color-signal)",
                        boxShadow: "0 0 24px oklch(0.64 0.22 18 / 30%)",
                      }}
                    >
                      {recording ? "Recording…" : "Flag Deposit"}
                    </button>
                    <button
                      className="ug-btn-ghost"
                      onClick={() => recordAndSetOutcome("allowed")}
                      disabled={recording}
                      style={{ flexShrink: 0, padding: "0 1rem" }}
                    >
                      Override / Allow
                    </button>
                  </>
                ) : (
                  <button
                    className="ug-btn-primary"
                    onClick={() => recordAndSetOutcome("allowed")}
                    disabled={recording}
                    style={{ flex: 1, justifyContent: "center" }}
                  >
                    {recording ? "Recording…" : "Allow Transaction"}
                  </button>
                )}
              </div>
              {recordError && (
                <p style={{ margin: "0 1.25rem 1rem", fontSize: "0.64rem", color: "var(--color-signal)" }}>
                  {recordError}
                </p>
              )}
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
                  ? "Deposit flagged. Recorded to the evidence ledger."
                  : "Deposit allowed. Recorded to the evidence ledger."}
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
                  Check another
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
