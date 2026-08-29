import { useCaseContext } from "@/store/case-context-store";
import { MOCK_CASES } from "@/lib/mock-data";
import { useState } from "react";

export function WalletSelector() {
  const { activeWallet, activeChain, setActiveWallet } = useCaseContext();
  const [isOpen, setIsOpen] = useState(false);

  // Get wallets from mock cases — only use fields that exist on InvestigationCase
  const wallets = Array.from(
    new Set(MOCK_CASES.map((c) => c.reportedWallet)),
  ).map((w) => w.replace("...", ""));

  const handleWalletSelect = (wallet: string) => {
    // Use current chain, or default to ETH if no chain is set
    const chain = (activeChain || "ETH") as
      "BTC" | "ETH" | "TRON" | "BSC" | "Polygon";
    setActiveWallet(wallet, chain);
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
          {wallets.map((wallet) => (
            <button
              key={wallet}
              onClick={() => handleWalletSelect(wallet)}
              style={{
                width: "100%",
                padding: "0.5rem 0.75rem",
                textAlign: "left",
                background:
                  activeWallet === wallet
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent",
                border: "none",
                borderBottom: "1px solid var(--border-subtle)",
                fontFamily: "var(--font-mono)",
                fontSize: "0.6rem",
                color:
                  activeWallet === wallet
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)",
                cursor: "pointer",
                transition: "all 0.12s",
              }}
              onMouseEnter={(e) => {
                if (activeWallet !== wallet) {
                  e.currentTarget.style.background = "oklch(0.98 0 0 / 2%)";
                  e.currentTarget.style.color = "var(--color-foreground)";
                }
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background =
                  activeWallet === wallet
                    ? "oklch(0.83 0.14 205 / 8%)"
                    : "transparent";
                e.currentTarget.style.color =
                  activeWallet === wallet
                    ? "var(--color-accent)"
                    : "var(--color-muted-foreground)";
              }}
            >
              {wallet}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
