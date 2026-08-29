# Unigraph — Real-Time Crypto Fraud Attribution System

**SIH26183 · MHA/I4C · Blockchain & Cybersecurity**

> Ingest victim-reported wallet addresses, trace blockchain activity, identify the nearest exchange/VASP, detect laundering patterns, and produce actionable intelligence for law enforcement.

---

## ⚡ Run in 5 minutes

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- (Frontend dev only) Node 20+

### 1. Clone and configure

```bash
git clone <repo-url>
cd unigraph
cp backend/.env.example backend/.env
# Edit backend/.env — at minimum set JWT_SECRET_KEY to a random value
```

### 2. Start the full backend stack

```bash
cd infra
docker-compose up --build
```

This starts:

| Service         | Port            | Notes                             |
| --------------- | --------------- | --------------------------------- |
| FastAPI backend | `8000`          | API + Swagger UI                  |
| PostgreSQL 15   | `5432`          | Relational store                  |
| Neo4j 5         | `7474` / `7687` | Graph database (browser at :7474) |
| Redis 7         | `6379`          | Risk registry + Celery broker     |

### 3. Verify it's up

```bash
curl http://localhost:8000/health
# → {"status":"ok","version":"0.1.0","services":{...}}

# Open Swagger UI
open http://localhost:8000/docs
```

### 4. Get a dev JWT (for testing protected endpoints via /docs)

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@unigraph.local","password":"devpass"}'
```

Copy the `access_token` → click **Authorize** in Swagger UI → paste as `Bearer <token>`.

---

## 📁 Structure

```
unigraph/
├── backend/         Backend Owner — FastAPI, Postgres, Neo4j, Redis, Celery, ML
├── frontend/        Frontend Owner — React + TS (separate README)
├── contracts/       JOINT — openapi.yaml + entities.md (source of truth)
├── infra/           docker-compose.yml + docker-compose.dev.yml
└── docs/            PRD, implementation plan, progress tracker
```

See [docs/unigraph-prd-v2.md](docs/unigraph-prd-v2.md) for the full product spec and [docs/implementation.md](docs/implementation.md) for the phase-by-phase build plan.

---

## 🔑 Dev credentials (Phase 0 only — replaced in Phase 2)

| Field        | Value                                  |
| ------------ | -------------------------------------- |
| Email        | `admin@unigraph.local`                 |
| Password     | `devpass`                              |
| Role         | `admin`                                |
| VASP API key | `dev_vasp_key_1` (header: `X-API-Key`) |

---

## 🛠 Common commands

```bash
# Backend only (for frontend dev against real API)
cd infra && docker-compose -f docker-compose.dev.yml up --build

# Run tests
cd backend && pip install -r requirements.txt
pytest

# Run Alembic migrations (after Phase 1 adds tables)
cd backend && alembic upgrade head

# Celery worker (Phase 2+)
cd backend && celery -A app.workers.celery_app worker --loglevel=info
```

---

## 🚦 Phase status

| Phase           | Status  | Description                                                         |
| --------------- | ------- | ------------------------------------------------------------------- |
| 0 — Scaffolding | ✅ Done | Contracts, FastAPI skeleton, docker-compose, /health, JWT stubs     |
| 1 — Correlation | ✅ Done | Complaint ingestion + Cross-Victim Correlation (NCRP)               |
| 2 — Registry    | ✅ Done | Redis registry + /check-wallet chokepoint (<200ms p95)              |
| 3 — Tracing     | ✅ Done | Multi-chain blockchain tracing (BTC, ETH, TRON) to nearest VASP     |
| 4 — ML Risk     | ✅ Done | XGBoost + SHAP evidence (Elliptic++ dataset, Test AUC-PR=0.954)     |
| 5 — Cases       | ✅ Done | Case management state machine + Forensic PDF reports                |
| 6 — LLM NER     | ✅ Done | Air-gapped Llama-3.2-3B on Ollama + deterministic spaCy fallback    |
| 7 — Hardening   | ✅ Done | Integration hardening, CORS, docker-compose verified, audit logging |

---

## ⚠️ Security reminders

1. `JWT_SECRET_KEY` **must** be overridden before any non-dev deployment.
2. `POSTGRES_PASSWORD` and `NEO4J_PASSWORD` defaults are insecure — override in production.
3. FIR/complaint narrative text **must never** leave the local network — only the local Ollama instance may receive it.
4. `/check-wallet` uses `X-API-Key` auth, **not** JWT — see `contracts/openapi.yaml`.
