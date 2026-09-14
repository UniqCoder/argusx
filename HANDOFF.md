# ARGUS — Session Handoff

Written 2026-09-14 to carry context into a new chat. Read this first before touching code.

## What ARGUS is

A blockchain-forensics investigation platform for Indian cyber-crime units (I4C/NCRP).
Frontend: React + TanStack Router/Start, `src/`. Backend: FastAPI + Postgres + Neo4j + Redis,
`sih-backend/backend/`, running in Docker (`sih-backend/infra/docker-compose.dev.yml`).

Branch: `truth-pass-and-v2-trace-groundwork`. Large uncommitted working tree — nothing in this
session was committed; that's consistent with how prior sessions on this branch worked too.
Don't assume everything below is committed; check `git status` before any destructive git op.

## How to run it

- Frontend dev server: `.claude/launch.json` has a config named `argus-frontend` (npm run dev,
  port 8080). Use `preview_start` with that name, don't run vite directly.
- Backend: already running in Docker — `docker ps` should show `argus_dev_backend`,
  `argus_dev_worker`, `argus_dev_postgres`, `argus_dev_neo4j`, `argus_dev_redis` all healthy.
  If not running: `docker compose -f sih-backend/infra/docker-compose.dev.yml up -d`.
- Login: Supabase auth gate on `/dashboard/*`. Dev credential is whatever the user signs in
  with on the landing page — I don't have credentials; every session so far has needed the
  user to physically sign in on the browser preview tab before dashboard pages are testable.
  Backend JWT bridge auto-authenticates as `investigator@i4c.gov.in` / `devpass` once Supabase
  session exists (see `src/store/session-store.ts`).
- The dev server frequently gets logged out on `preview_start`/hard reload — this is normal
  (Supabase session sometimes persists, sometimes doesn't across a fresh tab). Just ask the
  user to sign in again rather than assuming something is broken.

## Best demo wallet (has real victims + risk + everything wired)

`0x5eeded976510047d90301480bdc185122bfc7119` on **ETH** — seeded scenario "Telegram task-scam
syndicate": 3 victims (Maharashtra/Karnataka/Delhi), collector → mixer (Tornado Cash) + a
Polygon-bridge branch → Binance off-ramp. Exercises: fraudster/victim graph labeling, Cross-
Victim, Network Signals, Evidence Trail (has a real case, UG-1C4E94FB), Reports, Risk Intel.

Other seeded scenarios: `sih-backend/backend/app/services/scenarios/definitions.py` — 5 total,
also reachable by clicking a card in the "Investigation Scenarios" list on Trace Wallet.

Real (non-seeded) example addresses that hit live Etherscan/Tronscan: see `EXAMPLES` in
`src/routes/dashboard/trace.tsx`. These take real wall-clock time (live API calls) and can hit
transient `ReadTimeout`s from Etherscan — that's normal, not a bug (see below).

## What got fixed this session (chronological, high-signal only)

1. **Graph animation polish**: node-mount CSS entrance animation, camera auto-follow during
   replay (rAF-based, `src/components/dashboard/TraceGraph.tsx`), hover highlighting + tooltip,
   real-data-driven trace status text (`RESOLVING HOP N`, `TRACE COMPLETE`, etc. in
   `investigation.tsx`).
2. **Victim/Fraudster labeling — evidence-driven, not hardcoded.** The target (hop-0) node only
   gets `isSuspectedFraudster: true` when real linked complaints exist (`investigation.tsx`).
   Victim nodes are injected into the graph from real `useCorrelation` data at hop `-1`. See
   `src/lib/mock-data.ts` (`TraceNode.isSuspectedFraudster`), `src/lib/evidence.ts` (new —
   combined evidence-strength scoring from correlation + ML risk tier, documented thresholds).
3. **UI freeze — real root cause, found and fixed, WITH a self-caught regression**:
   `useWalletTrace` never aborted its streaming subscription on unmount, so abandoned traces
   kept running in the background. First fix (immediate abort) broke legitimate in-progress
   traces on route remount ("signal is aborted without reason" — a real regression I caught via
   live testing). Fixed with a 400ms debounced release instead (`src/hooks/use-wallet.ts`,
   `releaseTraceSubscription`/`RELEASE_GRACE_MS`). Verified with a live `PerformanceObserver`
   long-task instrumentation — zero long tasks under both active stress and idle conditions.
4. **Graph render perf**: streaming `onNode` events were rebuilding the ENTIRE graph (full
   layout relaxation + full SVG re-render) on every single streamed node — for a 35-node trace,
   that's the expensive work running 35x instead of once. Fixed by coalescing into one flush
   per animation frame (`use-wallet.ts`, `flushScheduled`/`flushRaf`). Verified: zero long tasks
   across a 35+ second real trace afterward. **Real traces are still slow because Etherscan
   itself is slow (sequential live API calls per hop) — that's not a rendering problem and
   can't be fixed client-side.**
5. **ML risk scoring — actually integrated and working now.** User supplied a zip with a
   trained `risk_model.joblib` + `wallet_embeddings.npz` (previously missing entirely — risk
   always returned N/A). Extracted into `sih-backend/backend/app/ml/artifacts/`. ALSO found and
   fixed a second blocker: the backend container had `numpy 2.4.6` live despite
   `requirements.txt` pinning `<2.0.0` (SHAP's C-extension needs the 1.x ABI) — every risk call
   was silently crashing at the SHAP step. Fixed via `docker exec argus_dev_backend pip install
   "numpy<2.0.0"` + `docker restart argus_dev_backend argus_dev_worker` (the underlying image
   was already correct; only the running container's writable layer had drifted from an ad hoc
   `pip install` sometime in its history — restart alone fixed it durably). **Verify risk
   scoring works** by checking numpy version in both containers before doing anything else:
   `docker exec argus_dev_backend python3 -c "import numpy; print(numpy.__version__)"` should
   print `1.26.4`. If someone rebuilds the image from scratch and it comes back wrong, redo the
   pip install + restart.
6. **Risk Intelligence page — 5 compounding display bugs, all fixed**
   (`src/routes/dashboard/risk.tsx`): missing "Low Risk" tier branch (anything <55 said "Medium
   Risk" even at score 0), badge hardcoded to critical/red styling regardless of actual tier,
   a "total N pts" header that was comparing the wrong two numbers (claimed factors summed to
   the 0-100 score; they don't — different units), percentages that divided by the wrong
   denominator (→ literal "Infinity%" at score 0), and SHAP-decreasing factors shown as bold red
   "+N" with no sign distinction from increasing ones. Added `RiskSignal.direction` field
   (`src/lib/mock-data.ts`), single `TIER_META` source of truth keyed off the backend's own
   `risk_tier`. Verified live on `0xb8aEccC3ab76a0a1FB807244205B1E3f88C86B89` (real wallet,
   score 0/low) — all correct now: badge "LOW", "Low Risk" text, real percentages, `−N` signs
   on decreasing factors, cyan (not red) coloring for them.
7. **Evidence Ledger / Deposit Watch flag → real case linkage.** "Recorded to the evidence
   ledger" was true but unverifiable: the deposit-decision ledger entry was always written with
   `case_id=None` because the only case reference Deposit Watch had (`case_ref`) is opaque
   free-text from the Redis risk registry, not a real DB foreign key — the backend correctly
   refused to fabricate a link from it. Fixed by adding a real `case_id: Optional[UUID]` field
   (`sih-backend/backend/app/schemas/check_wallet.py`,
   `sih-backend/backend/app/api/v1/routers/wallets.py`) that the frontend now populates from
   `useCaseContext().activeCaseId` when one exists (`src/routes/dashboard/deposit.tsx`).
   Verified end-to-end: flagged a deposit with case `UG-1C4E94FB` active → the entry now
   genuinely appears in that case's Evidence Trail (52 events, up from 51).

## Architectural notes worth knowing

- **Evidence Ledger** = `sih-backend/backend/app/engine/ledger.py`, `append_entry()`. Real,
  hash-chained (each entry links to the previous entry's hash), append-only. Every anchor,
  trace, risk decision, deposit decision writes here. Evidence Trail
  (`src/routes/dashboard/evidence.tsx`) reads it filtered by `case_id`.
- **Streaming trace**: `src/lib/trace-stream.ts` (SSE via `fetch` + `ReadableStream`, not
  `EventSource`, because auth needs a header). Consumed by `useWalletTrace` in
  `src/hooks/use-wallet.ts`, which has a module-level `_runs` dedup map keyed by
  `${chain}:${address}` so React's double-render doesn't start two real traces.
- **Graph node/edge model**: `src/lib/mock-data.ts` `TraceNode`/`TraceEdge`. Layout in
  `src/hooks/use-trace-layout.ts` (hop-layered, allows negative layers for victim nodes at
  hop -1). Rendering in `src/components/dashboard/TraceGraph.tsx`.
- **Evidence strength** (LOW/MEDIUM/HIGH shown on the fraudster panel):
  `src/lib/evidence.ts`, `computeEvidenceStrength()`. Combines victim-correlation score
  (`correlation_service.calculate_correlation_score`, backend) with the ML risk tier — HIGH
  requires either strong correlation alone, or two independent signals agreeing. Documented
  thresholds in the file itself.
- **Known-VASP registry**: `sih-backend/backend/app/services/explorers/known_vasps.py` — exact-
  match only, curated real entries (e.g. the TRON address `TLa2f6VPqDgRE67v1736s7bJ8Ray5wYjU7`
  IS a genuine Binance hot wallet in the registry, not a bug if a trace stops there instantly).

## Known non-bugs (don't re-investigate these, they're correct/expected)

- A trace stopping instantly at hop 0 because the address is a curated known-VASP entry.
- `EXPLORER_UNAVAILABLE` / "Explorer temporarily unavailable" banners — genuine transient
  `ReadTimeout`s talking to live Etherscan/Tronscan, not an app bug. 8s timeout + 1 retry is
  already the documented design (`eth_explorer.py`).
- `NODE_LIMIT` / "Trace budget reached" — the 30-35 address budget is a real, disclosed bound
  (see `runStreamingTrace` comment in `use-wallet.ts`), not a failure.
- Real (non-seeded) wallet traces taking many seconds/tens-of-seconds — that's live network
  I/O to public explorers, sequential by design, not a rendering problem.

## Not done / explicitly out of scope so far (flagged to user, not silently skipped)

- Network Signals page redesign, Evidence Trail DIRECT/CORRELATED/CONTEXTUAL categorization,
  Cross-Victim page redesign, graph node-grouping/collapsing for very large traces — all from
  an earlier giant master-prompt, explicitly deprioritized in favor of real bugs + the
  victim/fraudster work. Still outstanding if the user asks again.
- No separate "confidence" model exists in the backend — only `correlation_score` and the ML
  `risk_tier`. Don't invent a confidence number; the Investigation page already honestly shows
  "Confidence: Not available".
- File Complaint / Complaint Intake was deliberately deleted earlier this session per explicit
  user instruction ("remove file complaint") — don't re-add it unless asked.

## Working style notes for whoever picks this up

- The user gives large, sprawling multi-part prompts (sometimes copy-pasted master-prompts from
  elsewhere) mixed with terse follow-ups referencing screenshots/screen recordings. Read
  attachments literally — screen recordings can be frame-extracted with ffmpeg (bundled via
  `pip install imageio-ffmpeg`, binary at whatever `imageio_ffmpeg.get_ffmpeg_exe()` reports —
  opencv-python-headless alone could NOT decode these recordings, imageio-ffmpeg could).
- The user tests things themselves and will call out "still broken" — when that happens,
  actually re-verify live rather than re-explaining the same reasoning; twice this session an
  initial fix had a real edge case that only showed up under live testing, and being defensive
  instead of re-testing would have shipped a broken fix.
- Always `npx tsc --noEmit -p tsconfig.json` after any frontend edit; for backend edits, at
  minimum `docker exec argus_dev_backend python3 -c "import ast; ast.parse(open('/app/...').read())"`
  since there's no fast backend typecheck equivalent set up.
- This repo has real CRLF/formatting drift in some files (pre-existing, not yours to fix) — expect
  a wall of `prettier/prettier` CRLF lint noise on `eslint` runs; ignore it unless you introduced
  a genuine new formatting issue in code you wrote (check with `eslint --fix` on just the lines
  you touched, don't mass-reformat unrelated files).
