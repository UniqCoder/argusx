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

  clearContext: () => void;

  // Getters
  hasActiveCase: () => boolean;
}

export const useCaseContext = create<CaseContext>((set, get) => ({
  activeCaseId: null,
  activeCaseNumber: null,
  activeWallet: null,
  activeChain: null,
  activeFraudType: null,
  activeCaseStatus: null,

  setActiveCase: (params) =>
    set({
      activeCaseId: params.caseId,
      activeCaseNumber: params.caseNumber,
      activeWallet: params.wallet,
      activeChain: params.chain,
      activeFraudType: params.fraudType || null,
      activeCaseStatus: params.status || null,
    }),

  setActiveWallet: (wallet, chain) =>
    set({
      activeWallet: wallet,
      activeChain: chain,
    }),

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
