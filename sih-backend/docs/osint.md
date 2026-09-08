# osint.md — Argus Backend: Structured OSINT Lookup Module

The OSINT module (`backend/app/services/osint_service.py`) adds structured
public-source corroboration for wallet addresses evaluated by `/risk`. It is a
**real structured-source module**: every datum returned is a discrete, typed
field attributed to a specific source — never a free-text conclusion.

## Scope & boundaries

**In scope (shipped):**
- **ransomwhe.re** — public bulk JSON export (`https://api.ransomwhe.re/export`),
  no API key. Structured fields: `address`, `blockchain`, `family`
  (ransomware family label such as "Netwalker (Mailto)"), `created_at`,
  `updated_at`. Bundled snapshot at
  `backend/app/data/osint/ransomwhe_export.json` (rebuild with
  `python -m scripts.build_osint_snapshot`).
- **Bitcoin Abuse Database** — `https://www.bitcoinabuse.com`, free-tier API key
  required. Structured fields: `abuse_type` (ransomware / darknet market /
  blackmail scam / sextortion / other), report `created_at`, `reports_count`.

**Out of scope (deliberately deferred):**
- **Etherscan nametags** — the official `getaddresstag` endpoint is a paid
  Pro-Plus tier feature; no accessible public/API path exists to query it.
  Documented as out of scope rather than scraping the site.
- **Forum / social-media scraping** — no crawler, no unstructured parsing.
- **OpenAI/LLM authorship attribution** from free text — no conclusion derived
  from text bodies.

## How hits are surfaced

`lookup_address(chain, address)` checks, in priority order:
1. **Redis cache** (`osint:{chain}:{address}`, TTL 24h).
2. **In-memory index** of the bundled ransomwhe.re snapshot (no network).
3. **Bitcoin Abuse live check** — BTC only, and only if
   `BITCOINABUSE_API_KEY` is set in the environment.

Hits are typed `OsintHit(source, category, report_date, detail, reference_url)`
and are:
- appended to `RiskResponse.osint` (structured per-hit records), **and**
- mirrored into `RiskResponse.evidence` as an `osint.{source}` entry with
  `contribution = 0.0` and `direction = increases_risk`.

OSINT is **corroboration only**: it never changes `risk_score`, `risk_tier`, or
`risk_source` (`risk_source` remains `ml_model` or `sanctions_override`).

## Rate limits & request pattern

Bitcoin Abuse free tier is **30 requests/minute** (~1 request per 2 seconds).
This sets the hot-path design: `/risk` does **not** hit Bitcoin Abuse
per-request as a primary path. The default lookup is the Redis cache + in-memory
snapshot. The live Bitcoin Abuse `reports/check` call is only an uncached
fallback, throttled to ≥2.5s between calls, and capped at 10 reports per
address. Bulk CSV (`/download/30d`) is consumed only by the Celery sync task.

## Celery sync

`app.workers.tasks.osint_refresh.sync_osint_sources`:
- re-downloads the ransomwhe.re export, atomically rewrites the on-disk snapshot
  (temp-file rename), reloads the in-memory index, and re-primes all Redis keys;
- pulls the Bitcoin Abuse 30d bulk CSV and primes those keys (no-op if the API
  key is not set).

Register the module in `celery_app.py`'s `include` list (already done).
Fails safe: any source error is logged and the prior on-disk / Redis data is
retained. Restart the celery worker after editing worker code:

```
docker-compose -f infra/docker-compose.yml restart celery
```

## Configuration

`.env.example` (repo-root, `backend/`, and `infra/`) documents
`BITCOINABUSE_API_KEY`. To activate Bitcoin Abuse:

1. Copy `infra/.env.example` to `infra/.env` and set
   `BITCOINABUSE_API_KEY=<your-free-key>`
   (free tier: `https://www.bitcoinabuse.com` → Register → Settings → API).
2. `docker-compose -f infra/docker-compose.yml up -d` (recreates containers
   with the new env; `infra/.env` is gitignored).

No other key is required: ransomwhe.re is keyless, Etherscan is unused (the ETH
explorer uses keyless Blockscout), and `ETHERSCAN_API_KEY` / `TRONGRID_API_KEY`
are optional slots only.

## Tests

`backend/app/tests/test_osint.py`:
- snapshot lookup contract for a known ransomwhe.re address
  (`17TMc2UkVRSga2yYvuxSD9Q1XyB2EPRjTF`, family *Netwalker (Mailto)*);
- Redis-cache short-circuit;
- Bitcoin Abuse mocked 200/404/429 handling and key-disabled behaviour;
- `/risk` integration that OSINT evidence is surfaced without breaking the
  response.