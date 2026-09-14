// ============================================================
// Decimal wire-format helpers.
//
// The backend's forensic numeric fields are Python `Decimal`, which Pydantic
// serialises as a JSON **string** ("930.125872") so precision survives the
// wire. Integer fields (hops, counts) arrive as real JSON numbers.
//
// See the `Decimal` type in src/lib/api-types.ts for the history: these fields
// were typed as `number`, which was untrue at runtime, and went unnoticed
// because the only consumer interpolated them into template strings. The first
// real arithmetic on one threw "amount.toFixed is not a function" mid-trace and
// surfaced to the user as a bogus "Backend unreachable" error.
//
// Anything doing maths on, or formatting, a Decimal field goes through here.
// ============================================================
import type { Decimal } from "@/lib/api-types";

/**
 * Coerce a Decimal wire value to a number. Returns `fallback` for null,
 * undefined, or anything unparseable — never NaN, which would silently
 * propagate into rendered output as "NaN USDT".
 */
export function toNum(value: Decimal | null | undefined, fallback = 0): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : fallback;
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

/**
 * Format an on-chain amount with its asset ticker, using significant digits
 * rather than a fixed precision — 0.00040932 ETH and 691.53 USDT both have to
 * read correctly, and 930.125872 USDT should not render as "930.13" when the
 * exact figure is the evidence.
 */
export function formatAmount(
  value: Decimal | null | undefined,
  asset: string,
): string {
  const n = toNum(value, Number.NaN);
  if (!Number.isFinite(n)) return "—";
  const abs = Math.abs(n);
  const digits = abs === 0 ? 0 : abs < 0.001 ? 8 : abs < 1 ? 6 : 2;
  const text = digits === 0 ? "0" : n.toFixed(digits).replace(/\.?0+$/, "");
  return asset ? `${text} ${asset}` : text;
}

/** Compact form for counters and summaries (1.2K, 3.4M). */
export function formatCompact(value: Decimal | null | undefined): string {
  const n = toNum(value, Number.NaN);
  if (!Number.isFinite(n)) return "—";
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`;
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`;
  return formatAmount(n, "");
}
