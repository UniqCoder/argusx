# Known-Entity Allowlist Feasibility Report (Task 2 — assessment only, no implementation)

**Date:** 2026-09-05
**Scope:** Assess whether a public **tagged-address allowlist / known-entity registry**
can serve as a deterministic override layer (parallel to the block-based OOD
mitigation already documented in `docs/ml.md:315`) for the Satoshi-Genesis /
Ethereum-Foundation class of false positives. **No code was modified for this task.**

---

## 1. Existing deterministic-override pattern in this repo

The codebase already embraces a **defense-in-depth split**: the ML model "flags
unknowns, not entities" and an entity-level control layer handles known actors.

- `docs/ml.md:315` — "The defense-in-depth architecture (Redis registry for known
  entities, OFAC allow/block lists) handles these cases."
- `docs/unigraph-prd-v2.md` — Redis **risk registry** `risk:{chain}:{address}` with
  `allow / hold / block` actions; `/check-wallet` hot path consults the registry
  first (sub-200ms target, materialized view refreshed async).
- `backend/app/services/registry_service.py` + `backend/app/services/risk_service.py`
  — the wiring points where a deterministic allowlist override would slot in.

So a known-entity allowlist would be a **new deterministic registry consulted
before/after ML scoring**, mirroring how the block-based OOD mitigation (threshold
handling) already acts as a deterministic guard for a known failure mode.

---

## 2. Candidate public tagged-address sources

| Source | Chain | Format | Coverage / notes |
|---|---|---|---|
| **OFAC SDN List** | BTC/ETH (and others) | CSV/PDF w/ addresses | Sanctions-oriented; small curated set; authoritative, legally relevant |
| **Ethereum Foundation / official org addresses** | ETH | manual | Tiny; the two FP targets are already known |
| **Etherscan address labels (public CSV download)** | ETH | CSV | Community+official labels; large (100k+ labels ambiguous); staleness/accuracy risk |
| **WalletExplorer** | BTC | site/API | Clusters exchange entities; not a clean allowlist, has tagged addresses |
| **`ethereum-lists/addresses` (GH)** | ETH | JSON | Curated list of known wallets/blacklists/contracts |
| **exchange cold-wallet/public-address lists** | BTC/ETH | semi-official | Kraken, Binance, Coinbase public announcements; high-value allow entries |
| **TRONSCAN official labels** | TRON | API | Tagged addresses for TRON (chain already heuristic-only) |

## 3. Coverage reality vs the problem

The target class — "old + huge + legitimate" (Satoshi Genesis, Ethereum Foundation,
major exchange cold wallets, foundations) — is a **tiny, well-known set**. The vast
majority of live `/risk` queries are fresh victim-reported addresses that will never
be on any of these lists. So:

- **Hit-rate will be low** (likely <1% of traffic), but the hit-rate on the *specific
  false-positive class* is high (the two documented FPs are both globally famous).
- The allowlist does not replace the model; it **overrides a small, deterministic
  set** of addresses for which we have high-confidence external knowledge.

## 4. Design sketch (mirroring existing block-OOD mitigation)

1. **Store:** a small curated allowlist (chain, address, entity, reason, source, TTL)
   in the existing Redis registry namespace (`risk:{chain}:{address}` with
   `action=allow` + `reason_path=known_entity`) — reuse the existing registry
   materialization, no new infra.
2. **Lookup point:** in `risk_service.evaluate_wallet_risk` and `/check-wallet`
   registry path, consult the allowlist **before** ML scoring returns a NON-critical
   tier; if matched → return tier `low`/`allow` with an evidence entry noting the
   override (transparency) rather than cloth-covering the raw score.
3. **Safeguards:** override **only downgrades** (never upgrades a wallet to risk);
   maintain provenance (source URL, added-by, date) for audit; periodic refresh
   from source; a cap on list size to keep it curated.
4. **SPOF guard:** registry read is best-effort; on cache miss fall through to ML
   score exactly as today.

## 5. Risks / caveats

- **Spoofing / squatting:** an attacker could register an address that *looks like*
  a known entity (0x-prefix vanity, similar casing). Allowlist must compare exact
  full addresses, not prefixes, and verifiable via ECDSA/ens not just string shape.
- **Staleness / wrong tags:** community tag data (Etherscan) is noisy; a wrong
  `allow` on an actually-illicit address is worse than a false positive. Curated
  small set > bulk ingestion.
- **Address-space normalization:** BTC base58 vs ETH 0x-hex; TRON base58.
  Must normalize exactly at write and read time.
- **Case sensitivity:** ETH/TRON are case-insensitive checksummed; BTC base58 is
  case-sensitive. Must handle per-chain.
- **Legality/compliance:** OFAC integration should be treated as its own controlled
  dataset with review, not a silent ML override.

## 6. Feasibility verdict

**Feasible and low-effort — but narrow.** The right scope is a **small, curated
registry (a few hundred to low-thousand entries)** of globally-known entities
(exchanges, foundations, block winners, the two documented FP wallets), sourced
from official/public lists, used as a **downgrade-only deterministic override**
with provenance. It will not move the BTC AUC-PR/recall metrics (those are offline
labeled data without these live entities), but it will precisely eliminate the
Satoshi/ETH-Foundation-class false positives at the serving layer with bounded,
auditable risk.

**Recommendation:** implement in a follow-up as an extension of the existing Redis
registry (no schema/architecture change). This task requires **no code change** and
is reported as feasibility-only per the assignment.