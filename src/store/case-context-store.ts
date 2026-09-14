// ============================================================
// ARGUS — Case Context Store
// Tracks the "active case" and "active wallet" across all pages
// So Investigation → Risk Intelligence → Signals all show the SAME case
// ============================================================
import { create } from "zustand";

// A wallet this investigator actually searched/traced this session, recorded
// WITH the chain it was searched on. Storing the chain alongside the address
// is the fix for the chain-mismatch bug: selecting a recent wallet used to
// reuse whatever chain was currently active, so an ETH address could get
// traced as BTC (explorer failure -> "Backend unreachable") and the wallets
// table accumulated the same address under two different chains.
export interface RecentWallet {
  address: string;
  chain: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";
}

export interface CaseContext {
  // Active case being investigated
  activeCaseId: string | null;
  activeCaseNumber: string | null; // e.g., "UG-2026-04821"
  activeWallet: string | null; // e.g., "0x742d35Cc6634..."
  activeChain: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON" | null;
  activeFraudType: string | null; // e.g., "Investment Scam"
  activeCaseStatus: string | null; // e.g., "investigating"

  // Wallets this investigator has actually searched/traced this session —
  // real usage history (address + the chain it was searched on), not sample
  // data. Newest first, deduped on address+chain, capped.
  recentWallets: RecentWallet[];

  // Actions
  setActiveCase: (params: {
    caseId: string;
    caseNumber: string;
    wallet: string;
    chain: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";
    fraudType?: string;
    status?: string;
  }) => void;

  setActiveWallet: (
    wallet: string,
    chain: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON",
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

  // Result of looking up "does the wallet just traced already belong to a
  // case" (see investigation.tsx). Touches ONLY the case fields — never
  // activeWallet/activeChain, which the trace itself already set — so a
  // wallet with no case still traces normally, and a stale case from a
  // PREVIOUSLY traced wallet doesn't linger and misattribute this one's
  // Evidence Trail. Pass null when the lookup found no case.
  setCaseForWallet: (
    params: { caseId: string; caseNumber: string; status?: string } | null,
  ) => void;

  // Records a wallet (with the chain it was searched on) into the "recently
  // searched" history without touching activeWallet/activeChain — for lookups
  // (e.g. Cross-Victim's own search box) that shouldn't silently change what
  // the rest of the app considers "the active investigation."
  recordRecentWallet: (
    wallet: string,
    chain: "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON",
  ) => void;

  clearContext: () => void;

  // Getters
  hasActiveCase: () => boolean;
}

function pushRecent(
  list: RecentWallet[],
  wallet: string,
  chain: RecentWallet["chain"],
): RecentWallet[] {
  return [
    { address: wallet, chain },
    ...list.filter((w) => w.address !== wallet || w.chain !== chain),
  ].slice(0, 10);
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
      recentWallets: pushRecent(state.recentWallets, params.wallet, params.chain),
    })),

  setActiveWallet: (wallet, chain) =>
    set((state) => ({
      activeWallet: wallet,
      activeChain: chain,
      recentWallets: pushRecent(state.recentWallets, wallet, chain),
    })),

  setActiveCaseMeta: (params) =>
    set({
      activeCaseId: params.caseId,
      activeCaseNumber: params.caseNumber,
      activeFraudType: params.fraudType || null,
      activeCaseStatus: params.status || null,
    }),

  setCaseForWallet: (params) =>
    set(
      params
        ? {
            activeCaseId: params.caseId,
            activeCaseNumber: params.caseNumber,
            activeCaseStatus: params.status || null,
          }
        : {
            activeCaseId: null,
            activeCaseNumber: null,
            activeCaseStatus: null,
            activeFraudType: null,
          },
    ),

  recordRecentWallet: (wallet, chain) =>
    set((state) => ({
      recentWallets: pushRecent(state.recentWallets, wallet, chain),
    })),

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
