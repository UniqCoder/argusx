# Rules — Unigraph Backend (for AI coding agents, e.g. Antigravity)

## Engineering rules — non-negotiable

1. `contracts/openapi.yaml` is the source of truth. Never let a request/response shape drift from it — update the contract first, flag the change, then write code.
2. Strict layering: `routers/` (HTTP only) → `services/` (business logic) → `models/` + `graph/` + `nlp/` + `ml/` (data/ML access). Routers never touch SQLAlchemy or Neo4j directly.
3. `/check-wallet` is Redis-only in the hot path. No Postgres/Neo4j call may block that response — anything heavier goes through Celery, off the request path. Target: p95 < 200ms.
4. Every route returns the standard error envelope on failure — never a bare 500 or an HTML stack trace.
5. All primary keys exposed over the API are UUIDv4 strings — never leak Postgres serial ints.
6. All timestamps are ISO-8601 UTC, both directions.
7. `risk_tier`, case `status`, and alert `action` are the closed enums defined in `entities.md` — never invent a new value inline on either side.
8. FIR/complaint narrative text never leaves the local network except to the local Ollama instance — no external API call may ever receive it.
9. No secrets, API keys, or credentials committed to the repo — `.env.example` only; real values via environment variables.
10. An endpoint is only "done" once it's been verified via `/docs` or `curl` — not on the strength of code compiling.

## Working agreement with the Frontend Owner

- Any endpoint shape change = a conversation first, a contract edit second, code third.
- A silent shape change that breaks a frontend assumption is treated as a bug, not a refactor.

## Agent behavior rules (for Antigravity specifically)

1. Work one phase at a time, in the order given in `implementation.md`. Don't start Phase 4 ML work before Phase 0–1 are done — later phases depend on tables and services earlier phases create.
2. Before starting a task, check `progress.md`. If it's already `Done`, don't redo it — ask before overwriting.
3. After finishing a task, update `progress.md` yourself (status, date, one-line note) as part of that same turn — don't leave it for the human to do.
4. If a task needs a decision not covered in `implementation.md`, `rules.md`, or `datasets-and-ml.md` (e.g. "which explorer API to use", "exact SHAP library version"), stop and ask instead of guessing. Log it under `progress.md`'s Blockers table.
5. Don't add a library or service not already named in the stack without flagging it first and getting a yes.
6. Write a test (or at minimum a working `curl` example) for every endpoint before marking the task done.
7. Keep each change scoped to one task — don't bundle Phase 2 and Phase 3 work into one pass.
8. Never touch `frontend/` — that's outside backend scope for this project.
9. When uncertain about a real-world API (an explorer's response shape, a library's current interface), verify rather than assume from memory — outdated assumptions here break the hot-path latency target and the contract.
