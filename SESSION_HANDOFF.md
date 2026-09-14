# ARGUS — Session Handoff

Read this first in a new chat to pick up exactly where this session left off.
Paste this whole file (or its path) to the new session. This replaces the
previous handoff — everything below is current as of this write.

## Where things stand

Everything described below is **committed and pushed to `main`**
(`github.com/UniqCoder/argusx`, latest commit `f965627`) — nothing from this
session is sitting uncommitted. `main` is also what the connected Vercel
project (`argusx`) auto-deploys from on every push, and what the Railway
`argusx-backend` project's `backend`/`worker` services build from.

**The app is fully deployed and live** — see the "Live deployment" section
near the end of this file for URLs, architecture, every bug that was found
getting there, and exactly what to do if it breaks again. Read that section
before assuming anything is a new bug — most failure modes here have already
been hit once.

Local dev stack: `docker compose -f sih-backend/infra/docker-compose.dev.yml
up -d`, then `npm run dev` for the frontend. Dev login:
`investigator@i4c.gov.in` / `devpass`. The numpy version inside
`argus_dev_backend` must be `1.26.4` (SHAP's C-extensions need the 1.x ABI) —
check with `docker exec argus_dev_backend python3 -c "import numpy;
print(numpy.__version__)"` before assuming risk scoring is broken; if it's
drifted to 2.x, `docker exec argus_dev_backend pip install "numpy<2.0.0"` +
restart the backend/worker containers.

## What this session actually fixed (in rough chronological order)

**1. Risk score inconsistency, end to end.** The same wallet could show
different scores on Risk Intelligence vs. Deposit Watch vs. Cases vs.
seeded-demo traces. Root causes found and fixed for real, not papered over:
- Deposit Watch read a **separate, disconnected** Redis registry entry
  (hand-seeded per demo scenario, or never populated for real wallets) —
  totally independent of what Risk Intelligence computed live.
  `risk_service.evaluate_wallet_risk()` (`sih-backend/backend/app/services/
  risk_service.py`) is now the **single canonical scorer**, and it
  write-throughs its result to that same Redis registry on every call, with
  a `reason` string derived from its own real evidence — not a separately
  hand-written one that could drift.
- Sanctions hits used to hard-override to a flat `1.0`/`100` regardless of
  actual behavior. Now blended: `max(ml_score, 0.95)` — real ML evidence
  plus a documented floor, not a bare literal.
- Added a **complaint-corroboration** signal: 2+ independent NCRP/Sahyog
  complaints naming the same wallet floors the tier to HIGH (score floor
  0.60) — same mechanism as the sanctions floor, one tier down because a
  filed complaint is an unverified report, not a government designation.
  1 complaint alone gets a small additive bonus, no floor.
- CRITICAL tier now requires real backing (2+ complaints, a sanctions match,
  or an ML score so extreme it's self-corroborating ≥0.93) — a single
  moderate SHAP feature swing crossing 0.85 alone now shows HIGH, not
  CRITICAL.
- Precision was inconsistent across layers (API returned 4dp, Redis rounded
  to 3dp, Postgres column was `NUMERIC(4,3)`) — all now 4dp end to end
  (migration `0009_risk_score_precision`).
- **Seeded demo wallets were scoring off an empty feature vector** — the ML
  pipeline's own explorer calls don't know about the scenario fixture data
  the taint engine already uses for them, so every demo wallet hit a live
  Etherscan/Tronscan lookup for an address that's never existed on the real
  chain (always empty), and a near-all-zero vector reads as suspicious to
  this model. Fixed by checking `is_scenario_address()` first and routing to
  the same `FixtureExplorer` the taint engine uses. This is why all 5 demo
  cases used to saturate near 100 and now show honest, varied scores (only
  the 3-complaint scenario is HIGH; the rest are genuinely LOW).
- Every `RiskResponse` now carries `model_version` (content hash of the
  joblib artifact), `feature_schema_version` (hash of the column list),
  `snapshot_id` (hash of the exact model input + complaint/sanction state),
  and `calculated_at` — full traceability for "why does this say what it
  says, and would it say the same thing again."
- New tests in `test_risk.py`: same-snapshot determinism, cross-endpoint
  (`/risk` vs `/check-wallet`) identity, different-evidence-changes-score,
  no-artificial-clamping, SHAP-matches-the-scored-inference, and
  model/schema traceability.

**2. Plain-English risk evidence for investigators.** SHAP output ("SHAP:
2.644 (increases risk)") was correct but meaningless to a non-ML
investigator. `src/hooks/use-wallet.ts` now has a `FEATURE_STORY` glossary
translating ~20 model features into investigator vocabulary (collectors,
layering, fresh wallets, victim deposits) plus a strength label
(slight/moderate/strong/very strong) instead of the raw number. Sanctions
hits show the real OFAC designation text; complaint corroboration shows the
real complaint count and what it means.

**3. Risk-tier color consistency, everywhere.** One color mapping now used
by all four screens that show a score (`RISK_TIER_COLOR`/`riskTierColor()`
in `use-wallet.ts`) — previously Investigation hardcoded alarm-red
regardless of tier, Cases used its own score-threshold breakpoints that
disagreed with the backend's real 0.30/0.60/0.85 boundaries, and Deposit
Watch colored off `action` (a decision) rather than the real `risk_tier`.
Fixed a related graph bug at the same time: the reported/searched wallet
node was always rendered in the same red used for confirmed fraudsters,
regardless of whether any evidence actually supported that — it's now a
neutral gold "under investigation" color unless `isSuspectedFraudster` is
genuinely true (linked complaint, or a corroborated CRITICAL tier).

**4. Investigation graph: real controls, not just Play.** Added Prev/Next
buttons that step exactly one real transfer at a time, snapped to step
boundaries (`TraceControls` in `investigation.tsx`) — no more re-pressing
Play or imprecise scrub-bar dragging to review a trace.

**5. PDF case reports are now genuinely detailed.**
`report_service.py` gained: an executive stats strip (wallets, high/critical
count, complaints, total loss, addresses mapped), a full multi-hop
taint-trace section per wallet pulled from the real persisted `Trace`/
`TaintNode` rows (method, depth, termination reason, seed value, path-risk
breakdown, typologies detected, full node table with roles) instead of the
old flat single-hop lookup, a tamper-evident evidence-ledger section, and
full risk-score provenance (model/schema version, snapshot id) per wallet.
Also fixed two real bugs caught by actually reading the generated PDF: a
grammar bug in the complaint-corroboration text, and `₹` rendering as `■`
(ReportLab's default font has no glyph for it — switched to `INR` text).

**6. Removed unused `torch`/CUDA deps from `requirements.txt`.** GraphSAGE
(`app/ml/graphsage_risk.py`) is documented non-production research
(`docs/ml.md`) — the live `/risk` path never imports it. Installing PyPI's
default `torch` wheel pulls the full CUDA toolkit (a dozen `nvidia-cu12`
packages, several GB) into a CPU-only API image for zero benefit — this was
the actual root cause of Railway deploys silently failing after a
successful build with zero runtime logs (almost certainly OOM on a
free-tier container). `test_graphsage_fallback.py` now skips cleanly via
`pytest.importorskip("torch")` instead of failing collection.

## Known, already-disclosed, still-open items (don't rediscover these)

- "Every trace should start with a victim node" — not implemented for
  wallets with no linked complaint, because ARGUS has no real victim
  identity to show in that case, and fabricating a placeholder would
  violate the project's own "never fabricate evidence" principle used
  everywhere else. The reported-wallet node label was changed to "REPORTED
  — FUNDS SENT HERE" to make the actual convention explicit instead
  (the address you trace is where the victim's money WENT, not the
  victim's own wallet).
- Network Signals redesign, Evidence Trail DIRECT/CORRELATED/CONTEXTUAL
  categorization, Cross-Victim page redesign, graph node-grouping for very
  large traces — all explicitly deprioritized in earlier sessions, still
  outstanding if asked again.
- No separate "confidence" model exists in the backend — only
  `correlation_score` and the ML `risk_tier`. Investigation page honestly
  shows "Confidence: Not available" rather than inventing one.
- The model's real accuracy is modest and imbalanced-aware, not a bare
  headline percentage — see `docs/ml.md` if asked again: locked threshold
  0.70, combined test recall 42.0% / FPR 1.59%, strong on ETH (AUC-PR
  0.97), moderate on BTC (AUC-PR 0.47), zero labeled TRON training data
  (TRON scoring is heuristic-only).

## Working style notes for whoever picks this up

- The user gives large, sprawling multi-part prompts mixed with terse
  follow-ups. Read screenshots literally — several real bugs this session
  were only visible in a screenshot the user attached, not from a written
  description.
- The user tests things themselves and will push back sharply ("bro now
  every case is showing 100 ,, why not do it right in one go") — when that
  happens, actually re-verify live and find the real root cause rather than
  re-explaining prior reasoning. Twice this session an initial fix had a
  real edge case that only showed up under live testing.
- The user explicitly pushed back once on a request that would have
  re-introduced fake/arbitrary score clamping ("if low then it can be
  around 10 to 30") — held the line, explained why per the user's own
  earlier stated constraints, and the user accepted the real explanation
  instead (showing the actual SHAP evidence backing the low score) over a
  fabricated fix. Don't cave to "make it look more real" requests by
  faking numbers — find the real presentation/evidence gap instead.
- Always `npx tsc --noEmit -p tsconfig.json` after frontend edits; for
  backend edits, `MSYS_NO_PATHCONV=1 docker exec argus_dev_backend python3
  -m pytest app/tests/ -q --ignore=app/tests/test_graphsage_fallback.py` if
  torch isn't installed in that particular container image, otherwise drop
  the `--ignore` (it now skips cleanly either way as of this session).
  One pre-existing, unrelated flaky test:
  `test_trace.py::test_trace_wallet_tron_success` (a live-Tronscan network
  assertion) — don't try to fix it, it's not caused by anything in this repo.

## Live deployment

**Frontend**: `https://argusx.vercel.app` — Vercel project `argusx`
(`uniqcoders-projects` team), auto-deploys from `main`.

**Backend**: `https://backend-production-79b4.up.railway.app` — Railway
project `argusx-backend`, account `ombhirud123@gmail.com` (NOT
`zenonx128@gmail.com` — that's a different Railway account with an unrelated
`temporary-backend` project; don't touch it). Services: `backend` (FastAPI,
public domain), `worker` (Celery, no public domain), `Postgres` (managed),
`Redis` (managed). Both `backend` and `worker` build from
`sih-backend/backend/Dockerfile` via `source.rootDirectory: /sih-backend/backend`,
`build.builder: DOCKERFILE`.

**Graph DB**: Neo4j Aura Free (`https://console.neo4j.io`), NOT self-hosted
on Railway — see "Why not self-hosted Neo4j" below. Instance id `56df7916`.
**Its username is the instance id (`56df7916`), not the literal string
`"neo4j"`** — this cost real time to find; don't assume the default.

All real credentials (DB passwords, JWT secret, Neo4j password, VASP API
keys) live in Railway's **Variables** tab per-service — never re-derive or
guess them, and never put real secret values in this file or any committed
file. `railway variable list --service <name> --json` if you need to read
one (requires `railway login` as the correct account above).

### Config that made this work (don't undo it)

- `sih-backend/backend/app/core/config.py` / `main.py`: production CORS now
  reads `CORS_ALLOWED_ORIGINS` (exact origins, comma-separated) and
  `CORS_ALLOWED_ORIGIN_REGEX` (for Vercel preview-deployment subdomains)
  instead of the old bare `[]` that silently blocked every request. Both are
  set as Railway variables on `backend`.
- `backend`'s `deploy.startCommand`:
  `sh -c "uvicorn app.main:app --host 0.0.0.0 --port $PORT"` — the `sh -c`
  wrapper is required; Railway's exec-form command doesn't shell-expand
  `$PORT` on its own (cost real time to find — logs showed
  `Error: Invalid value for '--port': '$PORT' is not a valid integer`).
- `worker`'s `deploy.startCommand`:
  `celery -A app.workers.celery_app worker --loglevel=info --pool=solo` —
  `--pool=solo` is required. Default prefork concurrency auto-detects to the
  container's reported CPU count (was 48), and each forked worker process
  carries the full numpy/pandas/xgboost/spacy import footprint — that's an
  OOM on a small container. `solo` is single-process, which is fine for this
  app's actual background-task volume (alert notifications, registry
  refresh, OSINT sync — nothing high-throughput).
- `backend`/`worker`'s `DATABASE_URL` is **manually reconstructed** from
  Railway's individual Postgres variables with the async scheme:
  `postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.POSTGRES_PASSWORD}}@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}`
  — Railway's own `${{Postgres.DATABASE_URL}}` reference variable is the
  plain sync `postgresql://` scheme (psycopg2), and this app's SQLAlchemy
  engine is async (`create_async_engine`, needs `asyncpg`). Do NOT swap this
  back to the simpler `${{Postgres.DATABASE_URL}}` reference — it will
  break with `InvalidRequestError: The asyncio extension requires an async
  driver`.
- `sih-backend/backend/requirements.txt`: `torch`/`torch-geometric` were
  removed entirely (see the commit `727bf47` message). GraphSAGE
  (`app/ml/graphsage_risk.py`) is documented non-production research that
  the live `/risk` path never imports — installing PyPI's default `torch`
  wheel pulls the full CUDA toolkit (a dozen `nvidia-cu12` packages, several
  GB) into a CPU-only API image for zero benefit, and was the root cause of
  builds succeeding but the container then failing to even start (silently,
  zero deploy logs — almost certainly OOM). If GraphSAGE research resumes,
  install torch in a separate local environment, never back into this file.
- `sih-backend/backend/app/ml/artifacts/risk_model.joblib` and
  `wallet_embeddings.npz` are **committed to git**, overriding the general
  `*.joblib`/`*.npz` gitignore rule with an explicit allowlist in
  `sih-backend/.gitignore`. They used to be excluded on the theory they're
  "regenerable via `train.py`" — that's not actually true in this
  deployment, because the Elliptic++/Kaggle training datasets `train.py`
  needs are themselves not in the repo (multi-GB external downloads per
  `docs/ml.md`) and never will be. Without these two files committed, every
  `/risk` call on a fresh clone/deploy silently degrades to
  `risk_tier=unknown` — confirmed live, this exact thing happened and had
  to be diagnosed and fixed post-deploy. **If you ever retrain the model,
  commit the new `.joblib`/`.npz` over these — don't let them drift back out
  of git.**
- `main.py`'s `/health` endpoint logs `logger.warning(f"health_neo4j_down:
  {type(e).__name__}: {e}")` — deliberately an f-string in the event name,
  not `extra={"error": ...}`. The `extra=` kwarg wasn't reliably surfacing
  through the structlog/stdlib logging bridge in this production
  environment (logs showed the bare event name with no error detail at
  all), which cost real time while diagnosing the Neo4j auth failure below.
  If you add more health-check branches, follow the same f-string pattern,
  not `extra=`.
- Neo4j health-check timeout is `5.0`s, not `1.0`s — a hosted instance
  (Aura) is a real TLS+bolt handshake over the public internet, not a
  same-network container hop.

### Why not self-hosted Neo4j on Railway

A `neo4j:5-community` Docker service was tried first (own volume, own
password var). It failed to start with `java.io.IOException: No space left
on device` during its own system-database initialization — reproduced
**identically on a brand-new, completely empty volume**, and unaffected by
reducing the JVM heap/pagecache size (`256m`/`128m`). This is a genuine
Railway trial-plan resource ceiling, not a config bug — don't re-attempt
self-hosting Neo4j on this Railway account without upgrading the plan first.
Neo4j Aura Free was used instead and works fine at this data scale.

### Post-deploy steps that are NOT automatic — redo these if you ever spin up a fresh Postgres

A fresh Railway Postgres is genuinely empty — no tables, no data. `/health`
passing (`SELECT 1`) does NOT mean the app has real data; this cost real
confusion once already ("database is not reaching properly, showing no
cases" — the DB was reachable, just empty). After provisioning/replacing
Postgres:

1. **Run migrations.** No automatic migration-on-deploy exists yet. From a
   machine with the backend's Python deps (e.g. the local `argus_dev_backend`
   container) and Railway's Postgres reachable (see step 0 below):
   ```bash
   docker exec -e DATABASE_URL="postgresql+asyncpg://postgres:<PASSWORD>@<PROXY_HOST>:<PROXY_PORT>/railway" \
     argus_dev_backend bash -lc "cd /app && PYTHONPATH=/app alembic upgrade head"
   ```
2. **Seed demo data** (the 5 scenario cases/complaints/wallets), same
   container/env override:
   ```bash
   docker exec -e DATABASE_URL="..." argus_dev_backend bash -lc \
     "cd /app && PYTHONPATH=/app python -m scripts.reset_demo_data --seed-only"
   ```
3. **Step 0** for both of the above: Railway's Postgres has no public
   endpoint by default (private-network-only, correct default). Temporarily
   expose one to run these from a local machine:
   `railway service link Postgres && railway tcp-proxy create --service Postgres --port 5432 --json`
   — gives a `host:port` to plug into `DATABASE_URL` above. **Delete the
   proxy again when done**: `railway tcp-proxy delete <proxy-id> --service Postgres --yes`
   (get the id from `railway tcp-proxy list --service Postgres --json`).
   Don't leave a database's TCP proxy open longer than needed.
4. **Compute real risk scores for the seeded wallets.** Seeding only creates
   the case/complaint/wallet rows — it does not run ML scoring, so every
   seeded wallet starts with `risk_score: null` until something calls
   `/risk` for it. Hit the real live endpoint once per wallet (this also
   double-checks the ML artifacts + Aura connection are both working):
   ```bash
   curl -X POST https://backend-production-79b4.up.railway.app/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email":"investigator@i4c.gov.in","password":"devpass"}'
   # then for each seeded (address, chain):
   curl "https://backend-production-79b4.up.railway.app/api/v1/wallets/<address>/risk?chain=<chain>" \
     -H "Authorization: Bearer <token>"
   ```
   The 5 scenario (address, chain) pairs are in
   `sih-backend/backend/app/services/scenarios/definitions.py`
   (`ALL_SCENARIOS[i].anchor_address`, `.anchor_chain`).

### Known gap, not yet fixed

`sih-backend/backend/app/workers/tasks/registry_refresh.py`'s
`refresh_wallet_risk_task` still isn't dispatched from anywhere on a
schedule — the Redis risk-registry write-through that keeps Deposit Watch in
sync only happens synchronously inside `evaluate_wallet_risk()` (i.e. when
someone actually views Risk Intelligence for a wallet). That's sufficient
for demo purposes but means a wallet nobody has looked at since a fresh
deploy has no registry entry yet. A periodic Celery Beat schedule calling
this task for known/case-linked wallets would close that gap — not done
this session, flagged for whoever picks this up next.
