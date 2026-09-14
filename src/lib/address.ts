// Truncate a real wallet address for display only — never use the output of
// this function as a value sent back to the backend (it can't be traced).
export function truncateAddress(address: string, head = 6, tail = 4): string {
  if (address.length <= head + tail + 3) return address;
  return `${address.slice(0, head)}...${address.slice(-tail)}`;
}

// ── Per-chain input validation (client-side gate) ────────────────────────────
// Malformed input used to reach the backend and waste real explorer API calls,
// then render as a confusing empty/failed trace. These regexes keep garbage
// (pasted-twice hashes, elided placeholders like "0xE3B9...2D4A", wrong-chain
// shapes) out of the trace pipeline. Mirrored by a validator on the backend's
// AnchorCreate schema (app/schemas/engine.py) so the API 422s early too.

export type TraceInputChain = "BTC" | "ETH" | "TRON" | "BSC" | "POLYGON";

// EVM address: 0x + 40 hex chars. Checksum (EIP-55) intentionally not
// enforced — explorers treat addresses case-insensitively.
const EVM_ADDRESS_RE = /^0x[0-9a-fA-F]{40}$/;

// Bitcoin Base58Check (P2PKH "1…", P2SH "3…"): base58 alphabet excludes
// 0, O, I, l. Length 26-40 including the version byte.
const BTC_BASE58_RE = /^[13][1-9A-HJ-NP-Za-km-z]{25,39}$/;

// Bitcoin Bech32/Bech32m (P2WPKH/P2WSH/P2TR "bc1…"): BIP-173 charset
// excludes 1, b, i, o; all-lowercase per spec.
const BTC_BECH32_RE = /^bc1[023456789ac-hj-np-z]{11,71}$/;

// TRON address: base58check, "T" prefix, 34 chars total.
const TRON_ADDRESS_RE = /^T[1-9A-HJ-NP-Za-km-z]{33}$/;

// Transaction hashes: EVM hashes are 0x + 64 hex; BTC/TRON hashes are bare
// 64 hex. Hash-shaped anchors are accepted (the trace form advertises them)
// but resolve to a single honest node today — the taint engine walks from
// addresses.
const EVM_TX_HASH_RE = /^0x[0-9a-fA-F]{64}$/;
const BARE_TX_HASH_RE = /^[0-9a-fA-F]{64}$/;

export function isValidAddressFor(
  chain: TraceInputChain,
  value: string,
): boolean {
  const v = value.trim();
  switch (chain) {
    case "ETH":
    case "BSC":
    case "POLYGON":
      return EVM_ADDRESS_RE.test(v);
    case "BTC":
      return BTC_BASE58_RE.test(v) || BTC_BECH32_RE.test(v);
    case "TRON":
      return TRON_ADDRESS_RE.test(v);
  }
}

export function isValidTxHashFor(
  chain: TraceInputChain,
  value: string,
): boolean {
  const v = value.trim();
  if (chain === "ETH" || chain === "BSC" || chain === "POLYGON")
    return EVM_TX_HASH_RE.test(v);
  return BARE_TX_HASH_RE.test(v);
}

/** Address OR transaction hash, per chain — the trace form accepts both. */
export function isValidTraceInputFor(
  chain: TraceInputChain,
  value: string,
): boolean {
  return isValidAddressFor(chain, value) || isValidTxHashFor(chain, value);
}
