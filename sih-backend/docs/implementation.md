# Unigraph (SIH26183) — Backend Implementation Plan

**Owner:** Backend Owner (Rehan)
**Scope:** FastAPI service, PostgreSQL, Neo4j, Redis, Celery workers, ML pipeline, blockchain-explorer integrations, local LLM/NER, auth issuance, `/check-wallet` hook, PDF report generation.
**Not in scope:** React app internals, Tailwind theming, client-side state — that's the Frontend Owner's half. The only thing we build together is `contracts/openapi.yaml`.

---

## Stack

- FastAPI + Pydantic, SQLAlchemy + Alembic (Postgres), Neo4j (graph), Redis (risk registry + Celery broker), Celery (async workers)
- ML: XGBoost/LightGBM, Node2Vec/GraphSAGE + HDBSCAN, Louvain + PageRank, Isolation Forest
- LLM: Ollama (Llama-3-8B-Instruct), spaCy fallback
- Docker Compose for local + demo-day

## Non-negotiables (full list in `rules.md`)

1. `contracts/openapi.yaml` changes are never silent — loop in Frontend before, not after.
2. Every endpoint is verified via `/docs` or `curl` before it's marked done.
3. `/check-wallet` reads Redis only in the hot path — never Postgres/Neo4j synchronously.
4. Strict layering: `routers/` → `services/` → `models/` + `graph/` + `nlp/` + `ml/`.

---

## Phase 0 — Contract & Scaffolding (do this first, joint with Frontend)

**Goal:** a running skeleton both people can build against.

- [x] Write `contracts/openapi.yaml` for every route (with Frontend Owner)
- [x] Agree `contracts/entities.md` — `Wallet`, `Complaint`, `Case`, `Alert`, `RiskEvidence`, and the closed enums (`risk_tier`, case `status`, alert `action`)
- [x] Define the standard error envelope and apply it everywhere
- [x] Scaffold FastAPI app: `main.py`, `core/`, `api/v1/routers/`, `deps.py`
- [x] `docker-compose.yml`: postgres + neo4j + redis + backend
- [x] `/health` returns 200
- [x] JWT scaffolding (`/auth/login`, `/auth/refresh`) — shape only, real RBAC in Phase 2
      **Done when:** `docker-compose up` → `/health` = 200 and `/docs` is reachable.

## Phase 1 — Cross-Victim Correlation (USP 1 — build first)

**Goal:** cheapest end-to-end demo slice. No ML, no blockchain data needed.

- [x] `complaints` + `complaint_wallets` tables + Alembic migration
- [x] Synthetic-NCRP generator script (controlled shared-wallet duplication for the demo)
- [x] Deterministic correlation scoring (exact wallet match; fuzzy record-linkage optional later)
- [x] `POST /api/v1/complaints`
- [x] `POST /api/v1/correlate`
      **Sync point:** ship real `/correlate` mid-week; Frontend flips mocks off for that one route and diffs against the contract.

## Phase 2 — Risk Registry + Chokepoint (USP 2)

**Goal:** real-time hold/block decision — most demo-able slice without real blockchain infra.

- [x] Redis key shape: `risk:{chain}:{address} → {score, tier, case_ref, flagged_at, ttl}`
- [x] `POST /check-wallet` — API-key auth (not JWT), Redis-only hot path, p95 < 200ms
- [x] Mock VASP client simulating incoming deposits
- [x] `alerts` table + `GET /api/v1/alerts`
- [x] Celery task: on a hold decision, enqueue `alert_service.notify()` off the response path
      **Sync point:** review `/check-wallet` + `alerts` shapes together _before_ writing code — highest-value demo path.

## Phase 3 — Blockchain Tracing

- [x] BTC + ETH (+ TRON if time allows) explorer API integrations
- [x] Neo4j graph builder as a Celery async job (`Wallet`/`Transaction`/`VASP`/`Cluster`)
- [x] Nearest-VASP Cypher query (shortest `SENT→RECEIVED_BY→DEPOSITS_TO` path)
- [x] `GET /api/v1/wallets/{address}/trace`

## Phase 4 — ML Risk Scoring

- [x] Feature engineering: in/out-degree, tx velocity, volume in/out, wallet age, hop-distance to known-illicit cluster, correlation score (from Phase 1), fan-in/out counts, mixer-proximity flag, cross-chain bridge flag, avg tx value, time-of-day anomaly
- [x] Train XGBoost/LightGBM baseline on Elliptic/Elliptic++ (temporal split — see `datasets-and-ml.md`)
- [x] SHAP explainability wired into the evidence array shape
- [x] `GET /api/v1/wallets/{address}/risk`
- [x] Registry-refresh job materializing model output into `risk:{chain}:{address}`

## Phase 5 — Case Management + Reports

- [x] `cases` + `case_wallets` tables
- [x] `PATCH /api/v1/cases/{id}`
- [x] PDF report generation (case summary, evidence chain, linked complaints)
- [x] `GET /api/v1/cases/{id}/report`

## Phase 6 — LLM NER (USP 3, stretch — local air-gapped extraction)

- [x] Ollama + Llama-3.2-3B-Instruct locally, air-gapped (FIR text never leaves the intranet except to local Ollama; fits in 4GB GPU VRAM with sub-1.5s latency)
- [x] Structured JSON extraction prompt (names, amounts, wallets, dates, typology)
- [x] spaCy fallback/validator
- [x] Expose extracted entities read-only on the complaint-detail response — no new endpoint
      If GPU access isn't confirmed or LLM fails, fall back to deterministic spaCy/regex extractor.

## Phase 7 — Integration Hardening & Demo Prep

- [x] End-to-end run against the real backend (no mocks) for every screen
- [x] Error/loading states, CORS configured
- [x] `/check-wallet` load test — confirm p95 < 200ms
- [x] `docker-compose up` as the single demo-day command
- [x] Audit log verified on every case view/export

---

## 36-hour hackathon fallback

If the actual runway is one hackathon weekend, cut straight to: **Phase 1 → Phase 2 (mocked chokepoint) → single-chain tracing (list view is fine) → one static-threshold/rule-based risk score instead of a trained model → skip LLM NER**, describe it in the pitch as roadmap.
