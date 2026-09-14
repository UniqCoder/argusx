import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCaseContext } from "@/store/case-context-store";
import { isValidTraceInputFor } from "@/lib/address";
import { ScenarioPicker } from "@/components/dashboard/ScenarioPicker";
import type { ScenarioRead } from "@/lib/api-types";

export const Route = createFileRoute("/dashboard/trace")({
  component: TraceWallet,
});

const CHAINS = ["Ethereum", "Bitcoin", "TRON", "BSC", "Polygon"] as const;
type Chain = (typeof CHAINS)[number];

// `symbol` is the display ticker shown on the chain-selector buttons.
// `chainId` is the actual backend Chain identifier — these differ for TRON
// (ticker "TRX" vs. backend value "TRON"). Conflating the two used to mean
// every TRON trace request silently sent the wrong value.
const CHAIN_META: Record<
  Chain,
  { symbol: string; chainId: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON"; color: string }
> = {
  Ethereum: { symbol: "ETH", chainId: "ETH", color: "oklch(0.72 0.12 270)" },
  Bitcoin: { symbol: "BTC", chainId: "BTC", color: "oklch(0.79 0.15 74)" },
  TRON: { symbol: "TRX", chainId: "TRON", color: "oklch(0.64 0.22 18)" },
  BSC: { symbol: "BNB", chainId: "BSC", color: "oklch(0.84 0.14 90)" },
  Polygon: { symbol: "MATIC", chainId: "POLYGON", color: "oklch(0.72 0.18 290)" },
};

// Real addresses, each chosen to exercise a different genuine engine outcome.
//
// These descriptions were re-measured after the ERC-20 fix, because they had
// drifted from reality: the ETH entry was described as showing "multi-hop
// branching" but actually returned 5 nodes and 3 hops, because the explorer
// only read native-ETH value and every USDT transfer looked like a 0-value
// transaction. The same address now traces USDT ~6 hops to a Binance deposit.
//
//   ETH:  a wallet whose real activity is USDT — now traces ~19 addresses
//         across ~6 hops. Live, so the exact shape moves with the chain.
//   TRON: deep genuine TRC-20/TRX branching (tens of addresses).
//   BTC:  a known-VASP address. The engine attributes it to Binance at hop 0
//         and correctly stops there — a complete 1-node answer, not a failure,
//         and the workspace now explains that rather than showing a lone dot.
//
// A live trace walks one address at a time against public explorers, so it
// takes ~30-60s. The simulated demo case below is instant and is the one to
// use when the mixer / bridge / cross-chain / cross-victim paths need to be
// shown on demand.
const EXAMPLES = [
  {
    label: "ETH — Real Branching",
    addr: "0xb8aEccC3ab76a0a1FB807244205B1E3f88C86B89",
    chain: "Ethereum" as Chain,
    badge: "ug-badge--live",
  },
  {
    label: "TRON — Real Branching",
    addr: "TTaTPaA1TnQcXwCJ1jbMfkiUKdmuhVbUk6",
    chain: "TRON" as Chain,
    badge: "ug-badge--live",
  },
  {
    label: "BTC — Known VASP",
    addr: "34xp4vRoCGJym3xR7yCVPFHoCNxv4Twseo",
    chain: "Bitcoin" as Chain,
    badge: "ug-badge--live",
  },
];

// The backend only traces these three chains today — BSC/Polygon are UI
// options with no backend support yet, not silently-wrong data.
const BACKEND_SUPPORTED = new Set(["BTC", "ETH", "TRON"]);

function TraceWallet() {
  const [address, setAddress] = useState("");
  const [chain, setChain] = useState<Chain>("Ethereum");
  const navigate = useNavigate();
  const { setActiveWallet } = useCaseContext();

  const chainId = CHAIN_META[chain].chainId;
  const chainSupported = BACKEND_SUPPORTED.has(chainId);

  // Per-chain shape check BEFORE the backend is contacted — malformed input
  // (truncated "0xE3B9..." copies, wrong-chain shapes, stray characters)
  // used to reach the real explorers and come back as a confusing
  // "Backend unreachable"-style failure.
  const trimmedAddress = address.trim();
  const addressValid = isValidTraceInputFor(chainId, trimmedAddress);
  const canTrace = !!trimmedAddress && chainSupported && addressValid;

  // Loading a scenario is the same action as tracing any other wallet: set the
  // active wallet and navigate. There is no special path, no short-circuit and
  // no local fixture — the investigation page runs a real trace against the
  // real engine, which is why Cross-Victim, Deposit Watch, the report and the
  // evidence ledger all work on these cases.
  const loadScenario = (scenario: ScenarioRead) => {
    setActiveWallet(scenario.anchor_address, scenario.anchor_chain);
    navigate({ to: "/dashboard/investigation" });
  };

  const handleTrace = () => {
    if (!trimmedAddress || !chainSupported || !addressValid) return;
    // Set context from trace input, then navigate straight to the results
    // page — it fetches the real trace itself, no fake loading delay here.
    setActiveWallet(trimmedAddress, chainId);
    navigate({ to: "/dashboard/investigation" });
  };

  return (
    <div style={{ maxWidth: 680, margin: "0 auto" }}>
      {/* Header */}
      <div className="ug-page-header" style={{ justifyContent: "flex-start" }}>
        <div className="ug-page-header__left">
          <p className="ug-page-header__kicker">Trace Intelligence</p>
          <h1 className="ug-page-header__title">Trace Wallet</h1>
          <p className="ug-page-header__sub">
            Paste a wallet address or transaction hash to begin multi-hop
            tracing.
          </p>
        </div>
      </div>

      {/* Main input panel */}
      <div
        className="ug-surface"
        style={{ overflow: "hidden", marginBottom: "0.75rem" }}
      >
        <div className="ug-panel-header">
          <span className="ug-section-title" style={{ marginBottom: 0 }}>
            New Trace
          </span>
          <div className="ug-system-live" style={{ fontSize: "0.56rem" }}>
            <span className="ug-system-live__dot" />
            LIVE
          </div>
        </div>

        <div style={{ padding: "1.5rem" }}>
          {/* Address input */}
          <div style={{ marginBottom: "1.25rem" }}>
            <label
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                letterSpacing: "0.28em",
                textTransform: "uppercase",
                color: "var(--color-muted-foreground)",
                display: "block",
                marginBottom: "0.55rem",
              }}
            >
              Wallet Address or Transaction Hash
            </label>
            <input
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTrace()}
              placeholder="0x� or 1A1z� or T� or tx hash"
              autoFocus
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                background: "var(--bg-2)",
                border: "1px solid var(--border-strong)",
                borderRadius: "2px",
                fontFamily: "var(--font-mono)",
                fontSize: "0.9rem",
                color: "var(--color-foreground)",
                outline: "none",
                transition: "border-color 0.15s, box-shadow 0.15s",
                boxSizing: "border-box",
                letterSpacing: "0.04em",
              }}
              onFocus={(e) => {
                e.target.style.borderColor = "oklch(0.83 0.14 205 / 60%)";
                e.target.style.boxShadow =
                  "0 0 0 2px oklch(0.83 0.14 205 / 10%)";
              }}
              onBlur={(e) => {
                e.target.style.borderColor = "var(--border-strong)";
                e.target.style.boxShadow = "none";
              }}
            />
          </div>

          {/* Chain selector */}
          {trimmedAddress && !addressValid && (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-destructive, oklch(0.65 0.2 25))",
                marginTop: "-0.9rem",
                marginBottom: "1.5rem",
                lineHeight: 1.6,
              }}
            >
              Doesn't look like a valid {CHAIN_META[chain].symbol} address or
              transaction hash — check for truncation (…), stray characters,
              or the wrong chain selected above.
            </p>
          )}

          {/* Chain selector */}
          <div style={{ marginBottom: "1.5rem" }}>
            <label
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.58rem",
                letterSpacing: "0.28em",
                textTransform: "uppercase",
                color: "var(--color-muted-foreground)",
                display: "block",
                marginBottom: "0.55rem",
              }}
            >
              Blockchain
            </label>
            <div style={{ display: "flex", gap: "0" }}>
              {CHAINS.map((c, i) => {
                const meta = CHAIN_META[c];
                const isSelected = chain === c;
                const first = i === 0;
                const last = i === CHAINS.length - 1;
                return (
                  <button
                    key={c}
                    onClick={() => setChain(c)}
                    style={{
                      flex: 1,
                      padding: "0.5rem 0.25rem",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.64rem",
                      letterSpacing: "0.08em",
                      cursor: "pointer",
                      transition: "all 0.12s",
                      background: isSelected
                        ? `${meta.color.replace(")", " / 14%)")}`
                        : "var(--bg-2)",
                      borderTop: `1px solid ${isSelected ? meta.color.replace(")", " / 60%)") : "var(--border-strong)"}`,
                      borderBottom: `1px solid ${isSelected ? meta.color.replace(")", " / 60%)") : "var(--border-strong)"}`,
                      borderLeft: first
                        ? `1px solid ${isSelected ? meta.color.replace(")", " / 60%)") : "var(--border-strong)"}`
                        : `1px solid ${isSelected ? meta.color.replace(")", " / 60%)") : "var(--border-strong)"}`,
                      borderRight: last
                        ? `1px solid ${isSelected ? meta.color.replace(")", " / 60%)") : "var(--border-strong)"}`
                        : "none",
                      borderRadius: first
                        ? "2px 0 0 2px"
                        : last
                          ? "0 2px 2px 0"
                          : 0,
                      color: isSelected
                        ? meta.color
                        : "var(--color-muted-foreground)",
                      fontWeight: isSelected ? 700 : 400,
                    }}
                  >
                    {meta.symbol}
                  </button>
                );
              })}
            </div>
          </div>

          {!chainSupported && (
            <p
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: "0.68rem",
                color: "var(--color-destructive, oklch(0.65 0.2 25))",
                marginTop: "0.6rem",
              }}
            >
              {CHAIN_META[chain].symbol} tracing isn't supported by the
              backend yet — only BTC, ETH, and TRON are live.
            </p>
          )}

          {/* CTA */}
          <button
            className="ug-btn-primary"
            onClick={handleTrace}
            disabled={!canTrace}
            style={{
              width: "100%",
              justifyContent: "center",
              fontSize: "0.8rem",
              padding: "0.85rem",
            }}
          >
            START TRACE &rarr;
          </button>
        </div>
      </div>

      <ScenarioPicker onLoad={loadScenario} />

      {/* Example addresses */}
      <div
        className="ug-surface"
        style={{ overflow: "hidden", marginBottom: "0.75rem" }}
      >
        <div className="ug-panel-header">
          <span className="ug-section-title" style={{ marginBottom: 0 }}>
            Load Example
          </span>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.55rem",
              letterSpacing: "0.14em",
              color: "var(--color-accent)",
            }}
          >
            LIVE DATA
          </span>
        </div>
        {EXAMPLES.map((ex, i) => (
          <button
            key={ex.addr}
            onClick={() => {
              setAddress(ex.addr);
              setChain(ex.chain);
            }}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              width: "100%",
              padding: "0.75rem 1rem",
              background: "none",
              border: "none",
              borderBottom:
                i < EXAMPLES.length - 1
                  ? "1px solid var(--border-subtle)"
                  : "none",
              cursor: "pointer",
              textAlign: "left",
              transition: "background 0.12s",
            }}
            onMouseEnter={(e) =>
              (e.currentTarget.style.background = "oklch(0.98 0 0 / 2.5%)")
            }
            onMouseLeave={(e) => (e.currentTarget.style.background = "none")}
          >
            <div
              style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}
            >
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.74rem",
                  color: "var(--color-accent)",
                  letterSpacing: "0.04em",
                }}
              >
                {ex.addr.length > 14
                  ? `${ex.addr.slice(0, 6)}...${ex.addr.slice(-4)}`
                  : ex.addr}
              </span>
              <span
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.6rem",
                  color: "var(--color-muted-foreground)",
                }}
              >
                {ex.chain}
              </span>
            </div>
            <span className={`ug-badge ${ex.badge}`}>{ex.label}</span>
          </button>
        ))}
      </div>

      {/* Info strip */}
      <div
        style={{
          padding: "0.85rem 1rem",
          background: "oklch(0.83 0.14 205 / 5%)",
          border: "1px solid oklch(0.83 0.14 205 / 18%)",
          borderLeft: "2px solid var(--color-accent)",
          borderRadius: "2px",
          fontFamily: "var(--font-mono)",
          fontSize: "0.64rem",
          color: "var(--color-muted-foreground)",
          lineHeight: 1.65,
        }}
      >
        Traces run against live blockchain data (only BTC, ETH, and TRON are
        supported). Multi-hop paths, bridge interactions, and mixer proximity
        are automatically detected. Note: smart contracts and wallets that
        have only ever received funds legitimately produce a single-node
        result — that's a complete trace, not a failure. Results appear in
        the Investigation Workspace.
      </div>
    </div>
  );
}
