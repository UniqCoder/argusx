# ARGUS — Session Handoff

Read this first in a new chat to pick up exactly where this session left off.
Paste this whole file (or its path) to the new session. This replaces the
previous handoff — everything below is current as of this write.

## Where things stand

Branch: `truth-pass-and-v2-trace-groundwork` (on top of `main`). This branch
already has a merged-ready [PR #1](https://github.com/UniqCoder/argusx/pull/1)
open with 6 earlier commits (truth-pass mock-data removal, Celery async fix,
v2 engine groundwork, TRON bug fixes, ledger concurrency fix — all already
pushed). **This session's work (below) is UNCOMMITTED on top of that** — do
not lose it.

Docker stack (postgres, neo4j, redis, backend, worker) and the frontend dev
server were both running and healthy as of the last check. If a new session
finds them stopped:
```bash
docker compose -f sih-backend/infra/docker-compose.dev.yml up -d
```
then `npm run dev` for the frontend. Backend dev login:
`investigator@i4c.gov.in` / `devpass`. Real Supabase login is still uncertain
(email-quota status unknown) — the reliable way to get into the dashboard
for testing is the localStorage session-seed trick documented below.

## What prompted this session's work

User reported, after a "run prototype" demo: **the graph doesn't render,
there's no animation, Evidence Trail doesn't work**, and asked for a plan to
make every wallet trace reliably show a genuinely dynamic (not static, not
fake) graph. I diagnosed all three for real (not guessing) before writing a
plan, got it approved, and implemented all 4 parts. The approved plan is
still on disk: `C:\Users\Admin\.claude\plans\smooth-waddling-waterfall.md` —
read it for full rationale per part.

## What was done this session (uncommitted)

**A. Fixed the graph-invisible bug** (`src/styles.css`) — `.ug-workspace`'s
3-column grid (`232px 1fr 272px`) had no min-width, so the center graph
column collapsed to **0px** on any window narrower than ~504px. Fixed:
`.ug-workspace` now has `min-width: 960px` and `grid-template-columns: 232px
minmax(480px, 1fr) 272px`; `.ug-page` changed from `overflow-x: hidden` to
`overflow-x: auto` so it scrolls horizontally instead of clipping. **Verified
via direct DOM inspection** (`getBoundingClientRect()` on the trace SVG):
went from `{width: 0}` to genuinely rendering at real widths.

**B. Real chronological animation, not fake particles** — the old
`Math.random()` particle system was removed in an earlier session (it
animated fake "money flowing" unrelated to real data). Replaced with real
motion tied to real data:
- Backend: exposed `first_tainted_at` (already computed and persisted, just
  never returned) through `TaintNodeRead`/`TraceResult` — same pattern as
  the earlier `parent_address`/`tx_hash`/`tx_amount` exposure.
  (`app/schemas/engine.py`, `app/api/v1/routers/engine.py`)
- Frontend (`src/hooks/use-wallet.ts`, `src/routes/dashboard/investigation.tsx`):
  reveal order for Play/Replay/scrub now sorts by real `firstTaintedAt`
  (earliest first) instead of array/BFS order. Nodes fade+scale in
  (`opacity`/`transform` transitions), edges fade in, all tied to the real
  reveal step — no continuous fake pulsing.
- **Verified visually**: at progress=0 only the root node is visible, others
  faded/scaled down (0.35 opacity, 0.7 scale); scrubbing forward
  progressively reveals nodes in real chronological order. Screenshots
  confirmed this in-session.

**C. Real Evidence Trail** (was a placeholder before — no backend existed):
- Added nullable `case_id` FK to `Anchor` (→ `cases.id`, same pattern as
  `models/alert.py`), migration `0004_anchor_case_id` (**already applied**
  to the live dev DB — `alembic upgrade head` run this session).
- `create_anchor`/`run_trace` now persist `case_id` and pass it through to
  `ledger_engine.append_entry(..., case_id=...)` (the param already existed,
  just was never used by these 3 call sites) for `anchor_registered`/
  `trace_completed`/`decision_issued`. `Decision.case_id` also now set.
- New `ledger.get_entries_for_case()` helper (`app/engine/ledger.py`).
- New endpoint `GET /api/v1/cases/{id}/evidence` (`app/api/v1/routers/cases.py`)
  — merges the forensic ledger with the **already-existing, already-real**
  `audit_log` table (`app/services/audit_service.py`, was already recording
  `view_case`/`update_case_status`/`export_pdf_report` — I just hadn't
  noticed it existed until this session). New `EvidenceEvent` schema in
  `app/schemas/case.py`.
- Frontend: `useWalletTrace` now passes the active case's ID into anchor
  creation when one is selected (`src/hooks/use-wallet.ts`). Rewrote
  `src/routes/dashboard/evidence.tsx` to fetch and render this real feed
  (`getCaseEvidence` added to `src/lib/api.ts`), reusing the existing
  `.ug-timeline` CSS.
- **Verified fully working live**: created a real case, traced a wallet
  within it, opened Evidence Trail — saw real `Anchor Registered`/
  `Trace Completed`/`Decision Issued` events with **real decision reasoning
  text** ("Anchor present but evidence insufficient for a block (class=C,
  terminal=DUST, taint_fraction=0.002). Routed for manual review.") and a
  real `Case Viewed` audit-log entry, correctly merged and sorted.

**D. Honest "no outgoing activity" result instead of a bug-looking dead end**:
- Found and fixed a **real latent bug** along the way: `taint.py` used the
  raw string `"NO_OUTFLOW"` for non-root dead-end nodes, but that string was
  never added to the `TerminalKind` enum — the first real trace to hit that
  branch would have thrown a Pydantic validation error building the API
  response. Added `NO_OUTFLOW` to the enum properly (`app/schemas/engine.py`)
  and unified both the root (hop-0) and non-root "no outgoing transfers
  found" cases to use it (`app/engine/taint.py`) — previously the root case
  wrongly reused `NODE_LIMIT` (meant for "trace budget exhausted").
- Frontend (`investigation.tsx`): when a trace resolves to just the root
  node with `terminalKind === "NO_OUTFLOW"`, shows a clear explanatory
  panel instead of a lonely unexplained dot.
- **Verified live**: traced the USDT-TRC20 TRON contract address (which
  genuinely has no outgoing transfers as a contract) — the explanatory
  panel showed correctly: "TRACE COMPLETE — NO OUTGOING ACTIVITY FOUND...
  This is the complete, correct result for this address — not a failed
  trace."

**Bonus fix found while verifying C**: every real trace was silently firing
**two** real anchor-creation + trace requests (~5ms apart — confirmed via
duplicate `Anchor Registered` entries in the live Evidence Trail test, with
`source_ref` timestamps 5ms apart). Root cause not fully confirmed (no
`<StrictMode>` found in `src`, so likely a router/HMR remount rather than
React's dev-mode double-invoke) but the fix is defensive either way: added a
**module-level** (not component-level — survives remounts) in-flight-request
cache in `use-wallet.ts` (`_inflightTraces` Map, keyed by `chain:address`),
so a rapid double-fire for the same key reuses the same real request instead
of doubling real blockchain-explorer API calls (this was very likely also
contributing to the Tronscan rate-limiting hit earlier this session).

## What was NOT finished — do this first in the new session

**I was mid-verification of the dedup fix when interrupted.** Last thing I
did: traced the TRC20 contract address again post-fix and queried Postgres
for its anchors:
```
 dashboard-trace-1789200047301 | 2026-09-12 08:00:47.314415+00   <- post-fix trace, ONE anchor
 debug-check2-1789197350       | 2026-09-12 07:15:50.126686+00   <- old debug script
 debug-check-1789197255        | 2026-09-12 07:14:15.106407+00   <- old debug script
 dashboard-trace-1789197235669 | 2026-09-12 07:13:55.689037+00   <- pre-fix trace, PAIR (5ms apart)
 dashboard-trace-1789197235666 | 2026-09-12 07:13:55.675168+00   <- pre-fix trace, PAIR (5ms apart)
```
This looks like the fix worked (the most recent post-fix trace produced
exactly ONE anchor, not a pair) but I hadn't explicitly confirmed/concluded
this before being interrupted. **First step: re-run this exact check, or
trace one more wallet and confirm only one anchor gets created**, then
move on.

After that, finish the plan's verification checklist (nothing else should
be outstanding, but re-confirm before committing):
- Backend: `docker exec argus_dev_backend sh -c "cd /app && python -m pytest app/tests/ -q"` — baseline is 102 passed / 5 failed (same pre-existing ML-artifact-missing failures every time this session, unrelated to anything touched — do not try to fix those).
- Frontend: `npx tsc --noEmit` (ignore the 2 pre-existing `components/Experience.tsx`/`components/landing/` errors, unrelated/untouched), `npm run build`.
- Browser: re-verify the graph at a genuinely wide window too (only narrow + 1024px were explicitly checked this session).

## Then: commit and push

Nothing from this session is committed yet. Suggested split (or however
seems cleanest — no strong preference, just don't bundle unrelated fixes):
1. CSS layout fix (Part A) — small, standalone.
2. Real animation (Part B) — `first_tainted_at` exposure + reveal-order +
   transitions.
3. Real Evidence Trail (Part C) — migration + models + schema + routers +
   `evidence.tsx` rewrite.
4. `NO_OUTFLOW` bug fix + honest empty-state panel (Part D).
5. The anchor-dedup fix — probably bundle with whichever commit touches
   `use-wallet.ts` last, or standalone since it's a distinct bug.

Push to the same branch (`git push`, already tracks
`origin/truth-pass-and-v2-trace-groundwork`) — this updates PR #1 in place,
no new PR needed.

## Known, already-disclosed, still-open items (not from this session, don't rediscover these — just don't be surprised)

- Real Supabase login still unverified (quota status unknown — signup API
  call succeeds, can't confirm email delivery without a real inbox).
- ML risk model artifact + training data genuinely don't exist in the repo
  — `/wallets/{address}/risk` and Risk Intelligence page correctly show an
  honest error, not a fake score. Not fixable without sourcing real data.
- `registry_refresh_task` (would bridge computed ML risk → the Deposit
  Watch/`/check-wallet` Redis registry) still isn't dispatched from
  anywhere — Deposit Watch today only reflects the sanctions registry.
- BSC/Polygon chains correctly disabled in the UI (not implemented
  backend-side), not faked.
- v1 trace endpoint (`GET /wallets/{address}/trace`) still exists
  server-side (used internally by `report_service.py` + its own tests) but
  the frontend no longer calls it directly for the main Trace Wallet flow.
