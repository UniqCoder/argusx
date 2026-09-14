// ============================================================
// ARGUS — Chain identity and display
//
// The wire value and the human label are different things, and conflating them
// is how "Polygon" ended up in the frontend's Chain union while the backend
// enum said POLYGON — a mismatch that was being absorbed by `as` casts rather
// than fixed. `Chain` (src/lib/api-types.ts) is the wire value and must match
// app/schemas/common.py exactly; everything a person reads comes from here.
// ============================================================
import type { Chain } from "@/lib/api-types";

export const CHAIN_LABEL: Record<Chain, string> = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  TRON: "TRON",
  BSC: "BNB Chain",
  POLYGON: "Polygon",
};

export const CHAIN_TICKER: Record<Chain, string> = {
  BTC: "BTC",
  ETH: "ETH",
  TRON: "TRX",
  BSC: "BNB",
  POLYGON: "MATIC",
};

/**
 * Chains the engine can independently walk, because a live public explorer
 * exists for them (app/engine/taint.py `_LIVE_EXPLORERS`).
 *
 * POLYGON and BSC are deliberately absent. They appear in results only as the
 * destination side of a cross-chain hand-off, where the transactions come from
 * the seeded scenarios — a live Polygon address terminates as DEPTH_LIMIT and
 * says so, rather than pretending to have been traced.
 */
export const TRACEABLE_CHAINS: readonly Chain[] = ["BTC", "ETH", "TRON"];

export function isTraceable(chain: Chain): boolean {
  return TRACEABLE_CHAINS.includes(chain);
}

export function chainLabel(chain: string): string {
  return CHAIN_LABEL[chain as Chain] ?? chain;
}

export function chainTicker(chain: string): string {
  return CHAIN_TICKER[chain as Chain] ?? chain;
}
