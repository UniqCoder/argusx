// ============================================================
// ARGUS — Case Context Store
// Tracks the "active case" and "active wallet" across all pages
// So Investigation → Risk Intelligence → Signals all show the SAME case
// ============================================================
import { create } from "zustand";

export interface CaseContext {
  // Active case being investigated
  activeCaseId: string | null;
  activeCaseNumber: string | null; // e.g., "UG-2026-04821"
  activeWallet: string | null; // e.g., "0x742d35Cc6634..."
  activeChain: "BTC" | "ETH" | "TRON" | "BSC" | "Polygon" | null;
  activeFraudType: string | null; // e.g., "Investment Scam"
  activeCaseStatus: string | null; // e.g., "investigating"

  // Wallets this investigator has actually searched/traced this session —
  // real usage history, not sample data. Newest first, capped, deduped.
  recentWallets: string[];

  // Actions
  setActiveCase: (params: {
    caseId: string;
    caseNumber: string;
    wallet: string;
    chain: "BTC" | "ETH" | "TRON" | "BSC" | "Polygon";
    fraudType?: string;
    status?: string;
  }) => void;

  setActiveWallet: (
    wallet: string,
    chain: "BTC" | "ETH" | "TRON" | "BSC" | "Polygon",
  ) => void;

  // For pickers that only know case metadata (id/status/investigator) and
  // have no wallet to attach — the backend's case list doesn't join wallet
  // data, so this intentionally leaves activeWallet/activeChain untouched
  // rather than inventing a wallet.
  setActiveCaseMeta: (params: {
    caseId: string;
    caseNumber: string;
    fraudType?: string;
    status?: string;
  }) => void;

  // Records a wallet into the "recently searched" history without touching
  // activeWallet/activeChain — for lookups (e.g. Cross-Victim's own search
  // box) that shouldn't silently change what the rest of the app considers
  // "the active investigation."
  recordRecentWallet: (wallet: string) => void;

  clearContext: () => void;

  // Getters
  hasActiveCase: () => boolean;
}

function pushRecent(list: string[], wallet: string): string[] {
  return [wallet, ...list.filter((w) => w !== wallet)].slice(0, 10);
}

export const useCaseContext = create<CaseContext>((set, get) => ({
  activeCaseId: null,
  activeCaseNumber: null,
  activeWallet: null,
  activeChain: null,
  activeFraudType: null,
  activeCaseStatus: null,
  recentWallets: [],

  setActiveCase: (params) =>
    set((state) => ({
      activeCaseId: params.caseId,
      activeCaseNumber: params.caseNumber,
      activeWallet: params.wallet,
      activeChain: params.chain,
      activeFraudType: params.fraudType || null,
      activeCaseStatus: params.status || null,
      recentWallets: pushRecent(state.recentWallets, params.wallet),
    })),

  setActiveWallet: (wallet, chain) =>
    set((state) => ({
      activeWallet: wallet,
      activeChain: chain,
      recentWallets: pushRecent(state.recentWallets, wallet),
    })),

  setActiveCaseMeta: (params) =>
    set({
      activeCaseId: params.caseId,
      activeCaseNumber: params.caseNumber,
      activeFraudType: params.fraudType || null,
      activeCaseStatus: params.status || null,
    }),

  recordRecentWallet: (wallet) =>
    set((state) => ({ recentWallets: pushRecent(state.recentWallets, wallet) })),

  clearContext: () =>
    set({
      activeCaseId: null,
      activeCaseNumber: null,
      activeWallet: null,
      activeChain: null,
      activeFraudType: null,
      activeCaseStatus: null,
    }),

  hasActiveCase: () => {
    const state = get();
    return !!(state.activeCaseId && state.activeWallet && state.activeChain);
  },
}));
