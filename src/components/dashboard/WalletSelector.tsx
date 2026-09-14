import { useCaseContext, type RecentWallet } from "@/store/case-context-store";
import { truncateAddress } from "@/lib/address";
// Ticker shown next to each recent wallet so the operator can see which chain
// that address was searched on. Shared with every other surface via
// src/lib/chains.ts — this file used to keep its own copy, which is how "BSC"
// showed as "BSC" here and "BNB" elsewhere.
import { CHAIN_TICKER } from "@/lib/chains";
import { useState } from "react";

export function WalletSelector() {
  const { activeWallet, setActiveWallet, recentWallets } = useCaseContext();
  const [isOpen, setIsOpen] = useState(false);

  const wallets = recentWallets;

  // Restores BOTH the address and the chain it was searched on. Reusing the
  // currently-active chain here was the chain-mismatch bug: an ETH address
  // could get traced as BTC and vice versa, making the backend query the
  // wrong explorer and the whole trace fail with "Backend unreachable".
  const handleWalletSelect = (entry: RecentWallet) => {
    setActiveWallet(entry.address, entry.chain);
    setIsOpen(false);
  };

  return (
    <div style={{ position: "relative" }}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          padding: "0.5rem 0.75rem",
          background: "var(--bg-2)",
          border: "1px solid var(--border-strong)",
          borderRadius: "2px",
          fontFamily: "var(--font-mono)",
          fontSize: "0.65rem",
          color: "var(--color-accent)",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
          gap: "0.4rem",
          whiteSpace: "nowrap",
        }}
      >
        <span>
          {activeWallet ? activeWallet.slice(0, 10) + "..." : "Select wallet"}
        </span>
        <span style={{ fontSize: "0.5rem" }}>▼</span>
      </button>

      {isOpen && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            background: "var(--bg-0)",
            border: "1px solid var(--border-strong)",
            borderRadius: "2px",
            marginTop: "0.25rem",
            minWidth: "200px",
            zIndex: 50,
            boxShadow: "0 4px 12px rgba(0,0,0,0.15)",
          }}
        >
          {wallets.length === 0 && (
            <p
              style={{
                padding: "0.65rem 0.75rem",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color: "var(--color-muted-foreground)",
                  maxWidth: 220,
              }}
            >
              No wallets searched yet this session.
            </p>
          )}
          {wallets.map((entry) => (
            <button
              key={`${entry.chain}:${entry.address}`}
              onClick={() => handleWalletSelect(entry)}
              style={{
                width: "100%",
                padding: "0.5rem 0.75rem",
                textAlign: "left",
                background:
                  activeWallet === entry.address
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent",
                border: "none",
                borderBottom: "1px solid var(--border-subtle)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color:
                  activeWallet === entry.address
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)",
                cursor: "pointer",
                transition: "all 0.12s",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: "0.5rem",
              }}
              onMouseEnter={(e) => {
                if (activeWallet !== entry.address) {
                  e.currentTarget.style.background = "oklch(0.98 0 0 / 2%)";
                  e.currentTarget.style.color = "var(--color-foreground)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background =
                  activeWallet === entry.address
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent";
                e.currentTarget.style.color =
                  activeWallet === entry.address
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)";
              }}
            >
              <span>{truncateAddress(entry.address)}</span>
              <span
                style={{
                  fontSize: "0.52rem",
                  letterSpacing: "0.08em",
                  opacity: 0.7,
                  flexShrink: 0,
                }}
              >
                {CHAIN_TICKER[entry.chain]}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
