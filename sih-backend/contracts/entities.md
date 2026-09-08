# Argus — Shared Entity Vocabulary

> **Source of truth:** PRD §8.2. Both Pydantic schemas (backend) and TypeScript types (frontend) reference these definitions — never redefine an enum independently on either side.

---

## Entities

### `Wallet`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDv4 string` | Never leak Postgres serial int |
| `address` | `string` | Raw blockchain address |
| `chain` | `string` | `"BTC" \| "ETH" \| "TRON" \| "BSC"` |
| `risk_score` | `number` | `0.000–1.000` |
| `risk_tier` | `RiskTier` | See closed enum below |
| `vasp_identified` | `string \| null` | Name of nearest exchange/VASP, if known |
| `cluster_id` | `UUIDv4 string \| null` | Wallet cluster membership |
| `first_seen` | `ISO-8601 UTC string \| null` | |
| `last_seen` | `ISO-8601 UTC string \| null` | |

### `Complaint`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDv4 string` | |
| `ncrp_ref` | `string \| null` | |
| `source_platform` | `string` | `"ncrp" \| "sahyog" \| "manual"` |
| `narrative_text` | `string \| null` | NEVER sent to any external API — local LLM only |
| `fraud_typology` | `string \| null` | |
| `amount_lost` | `number \| null` | |
| `filed_at` | `ISO-8601 UTC string` | |
| `state` | `string \| null` | |
| `district` | `string \| null` | |
| `created_at` | `ISO-8601 UTC string` | |

### `Case`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDv4 string` | |
| `status` | `CaseStatus` | See closed enum below |
| `assigned_investigator` | `string \| null` | |
| `opened_at` | `ISO-8601 UTC string` | |
| `closed_at` | `ISO-8601 UTC string \| null` | |

### `Alert`
| Field | Type | Notes |
|---|---|---|
| `id` | `UUIDv4 string` | |
| `wallet_id` | `UUIDv4 string` | |
| `case_id` | `UUIDv4 string \| null` | |
| `triggered_by` | `string` | `"check_wallet_hook" \| "registry_refresh" \| "manual"` |
| `action` | `AlertAction` | See closed enum below |
| `created_at` | `ISO-8601 UTC string` | |
| `resolved_at` | `ISO-8601 UTC string \| null` | |

### `RiskEvidence`
| Field | Type | Notes |
|---|---|---|
| `feature_name` | `string` | e.g. `"fan_in_count_1h"` |
| `contribution` | `number` | SHAP value magnitude |
| `direction` | `string` | `"increases_risk" \| "decreases_risk"` |

---

## Closed Enums

### `RiskTier`
```
critical | high | medium | low | unknown
```
Maps exactly to the UI palette in PRD §14.1:
| Value | Hex | Meaning |
|---|---|---|
| `critical` | `#EF4444` | Immediate action required |
| `high` | `#F97316` | Escalate |
| `medium` | `#F59E0B` | Monitor closely |
| `low` | `#22C55E` | Acceptable risk |
| `unknown` | `#64748B` | Insufficient data |

### `CaseStatus`
```
new | investigating | escalated_to_vasp | frozen | closed
```
Maps exactly to Kanban columns in PRD §14.2.

### `AlertAction`
```
allow | hold | block
```
Returned by `/check-wallet` and stored on `Alert` records.

---

## Cross-cutting conventions

| Convention | Rule |
|---|---|
| IDs | UUIDv4 strings — never Postgres serial ints |
| Timestamps | ISO-8601 UTC, both directions |
| Versioning | All routes under `/api/v1/...` |
| Auth | `Authorization: Bearer <JWT>` on every route except `/api/v1/auth/login` and `/check-wallet` |
| Error envelope | `{ "error": { "code": "string", "message": "string", "details": {} } }` |
| Pagination | `?page=1&page_size=25` → `{ "items": [...], "total": N, "page": 1, "page_size": 25 }` |

---

## Changelog

| Date | Change | Requested by |
|---|---|---|
| 2026-08-28 | Initial definition — all entities and enums from PRD §8.2 | Backend Owner (Phase 0) |
