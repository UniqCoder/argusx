import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState } from "react";
import { useCaseContext } from "@/store/case-context-store";

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
  { symbol: string; chainId: "BTC" | "ETH" | "TRON" | "BSC" | "Polygon"; color: string }
> = {
  Ethereum: { symbol: "ETH", chainId: "ETH", color: "oklch(0.72 0.12 270)" },
  Bitcoin: { symbol: "BTC", chainId: "BTC", color: "oklch(0.79 0.15 74)" },
  TRON: { symbol: "TRX", chainId: "TRON", color: "oklch(0.64 0.22 18)" },
  BSC: { symbol: "BNB", chainId: "BSC", color: "oklch(0.84 0.14 90)" },
  Polygon: { symbol: "MATIC", chainId: "Polygon", color: "oklch(0.72 0.18 290)" },
};

// Real addresses, verified end-to-end against the live v2 taint-propagation
// engine — chosen specifically because each demonstrates a different real
// engine capability, not just "this string parses":
//   ETH:  a real wallet with genuine outgoing branching (multi-hop, several
//         active + dust-terminated children)
//   TRON: a real wallet with deep genuine branching (40+ nodes across 6 hops)
//   BTC:  a real known-VASP address — the engine attributes it to Binance
//         at hop 0 from the live known-entity registry, not a guess
// (A contract address like a token contract, or a wallet that's only ever
// received funds, will honestly show 0 outgoing hops — that's correct
// behavior, not a bug, so these three were picked to avoid that dead end.)
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

  const handleTrace = () => {
    if (!address.trim() || !chainSupported) return;
    // Set context from trace input, then navigate straight to the results
    // page — it fetches the real trace itself, no fake loading delay here.
    setActiveWallet(address, chainId);
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
            disabled={!address.trim() || !chainSupported}
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

      {/* Example addresses */}
      <div
        className="ug-surface"
        style={{ overflow: "hidden", marginBottom: "0.75rem" }}
      >
        <div className="ug-panel-header">
          <span className="ug-section-title" style={{ marginBottom: 0 }}>
            Load Example
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
        Traces run against live blockchain data. Multi-hop paths, bridge
        interactions, and mixer proximity are automatically detected. Results
        appear in the Investigation Workspace.
      </div>
    </div>
  );
}
