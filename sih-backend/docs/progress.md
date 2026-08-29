# Progress Tracker — Unigraph Backend

Update this after every work session — status, date, one-line note per task. Status values: `Not started` / `In progress` / `Blocked` / `Done`.

## Phase 0 — Contract & Scaffolding

| Task                    | Status | Date       | Notes                                                                                         |
| ----------------------- | ------ | ---------- | --------------------------------------------------------------------------------------------- |
| openapi.yaml drafted    | Done   | 2026-08-28 | OpenAPI 3.0.3 spec for all PRD §11 routes with security schemes & examples                    |
| entities.md agreed      | Done   | 2026-08-28 | Closed enums (RiskTier, CaseStatus, AlertAction, etc.) per PRD §8.2                           |
| Error envelope defined  | Done   | 2026-08-28 | Standard error envelope configured on global & validation exception handlers                  |
| FastAPI scaffold        | Done   | 2026-08-28 | Layered architecture (core/, api/, schemas/, models/, services/, graph/, ml/, nlp/, workers/) |
| docker-compose skeleton | Done   | 2026-08-28 | docker-compose.yml + docker-compose.dev.yml (postgres, neo4j, redis, backend)                 |
| /health endpoint        | Done   | 2026-08-28 | GET /health verified returning 200 and service connectivity reports                           |
| JWT scaffolding         | Done   | 2026-08-28 | /auth/login and /auth/refresh with token encoding/decoding and protected route guards         |

## Phase 1 — Cross-Victim Correlation

| Task                                            | Status | Date       | Notes                                                                             |
| ----------------------------------------------- | ------ | ---------- | --------------------------------------------------------------------------------- |
| complaints/complaint_wallets tables + migration | Done   | 2026-08-28 | Created Alembic migration 0001_phase1_tables matching entities.md & PRD §9.4 DDL  |
| Synthetic NCRP generator                        | Done   | 2026-08-28 | Standalone CLI script planting controlled shared-wallet clusters & single victims |
| Correlation scoring logic                       | Done   | 2026-08-28 | Deterministic scoring curve based on complaint count & distinct geographic spread |
| POST /api/v1/complaints                         | Done   | 2026-08-28 | Complaint ingestion & paginated listing with state/typology filtering             |
| POST /api/v1/correlate                          | Done   | 2026-08-28 | Exact wallet matching across complaints, geography aggregation, and total amount  |

## Phase 2 — Risk Registry + Chokepoint

| Task                              | Status | Date       | Notes                                                                                               |
| --------------------------------- | ------ | ---------- | --------------------------------------------------------------------------------------------------- |
| Redis registry key design         | Done   | 2026-08-28 | Designed risk:{chain}:{address} schema with allow/hold/block action determination                   |
| POST /check-wallet                | Done   | 2026-08-28 | Real-time chokepoint hook with X-API-Key auth, Redis-only hot path, and async Celery alert dispatch |
| Mock VASP client                  | Done   | 2026-08-28 | CLI client (mock_vasp_client.py) for single checks, seeding, and latency load testing               |
| alerts table + GET /api/v1/alerts | Done   | 2026-08-28 | Alerts ORM table, alert_service, and GET /api/v1/alerts with resolution filtering                   |
| Celery notify task                | Done   | 2026-08-28 | Async notify_alert_task off the response path recording alerts in PostgreSQL                        |

## Phase 3 — Blockchain Tracing

| Task                                | Status | Date       | Notes                                                                                                                                                    |
| ----------------------------------- | ------ | ---------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| BTC explorer integration            | Done   | 2026-08-28 | Blockstream Esplora REST API integration with UTXO vin/vout parsing                                                                                      |
| ETH explorer integration            | Done   | 2026-08-28 | Blockscout v2 REST API integration with exchange metadata tag resolution                                                                                 |
| TRON explorer integration           | Done   | 2026-08-29 | Tronscan REST API integration; TRON-PRO-API-KEY header; live verified on TLa2f... (Binance Hot); rate limit: 15 req/s with key (5 req/s unauthenticated) |
| Neo4j graph builder (Celery)        | Done   | 2026-08-28 | Async build_graph_task for multi-hop graph population off request path                                                                                   |
| Nearest-VASP Cypher query           | Done   | 2026-08-28 | Shortest path query (SENT -> RECEIVED_BY -> DEPOSITS_TO) with VASP entity attribution                                                                    |
| GET /api/v1/wallets/{address}/trace | Done   | 2026-08-28 | Multi-hop tracing endpoint returning TraceResponse with nearest VASP discovery                                                                           |

## Phase 4 — ML Risk Scoring

| Task                               | Status | Date       | Notes                                                                                                                                     |
| ---------------------------------- | ------ | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Feature engineering                | Done   | 2026-08-28 | 55-feature schema matching Elliptic++ Actors Dataset with strict code assertion guard                                                     |
| XGBoost baseline trained           | Done   | 2026-08-28 | 3-way temporal split (train 1-29, val 30-34, test 35-49). Threshold locked at 0.65 on Val (FPR=0.86%), Test AUC-PR=0.9543, Test FPR=0.90% |
| SHAP evidence output               | Done   | 2026-08-28 | TreeExplainer generating feature_name, contribution magnitude, and direction                                                              |
| GET /api/v1/wallets/{address}/risk | Done   | 2026-08-28 | Live risk scoring endpoint returning RiskResponse (score, tier, evidence array)                                                           |
| Registry-refresh job               | Done   | 2026-08-28 | Celery task updating risk:{chain}:{address} in Redis for instant hot-path lookup                                                          |

## Phase 5 — Case Management + Reports

| Task                          | Status | Date       | Notes                                                                                                      |
| ----------------------------- | ------ | ---------- | ---------------------------------------------------------------------------------------------------------- |
| cases/case_wallets tables     | Done   | 2026-08-28 | Schema matches entities.md CaseStatus enum (new, investigating, escalated_to_vasp, frozen, closed)         |
| PATCH /api/v1/cases/{id}      | Done   | 2026-08-28 | State machine validated transitions with standard error envelope on invalid transition                     |
| PDF report generation         | Done   | 2026-08-28 | ReportLab forensic report with Case summary, Phase 4 SHAP evidence, Phase 3 trace, Phase 1 NCRP complaints |
| GET /api/v1/cases/{id}/report | Done   | 2026-08-28 | Binary PDF streaming endpoint with Content-Disposition headers                                             |

## Phase 6 — LLM NER (Air-Gapped Llama-3.2-3B + spaCy)

| Task                         | Status | Date       | Notes                                                                                                                                             |
| ---------------------------- | ------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ollama + Llama-3.2-3B setup  | Done   | 2026-08-29 | 100% GPU offload on RTX 2050 (2.3GB VRAM). Warm throughput: 46.4 tok/s. Cold-start: ~7.8s, Warm-state: ~2.8s–3.2s for ~130-token structured JSON. |
| Structured extraction prompt | Done   | 2026-08-29 | JSON extraction pulling suspect names, normalized INR amounts, crypto wallets, dates, and typologies                                              |
| spaCy fallback               | Done   | 2026-08-29 | Deterministic regex + spaCy rule-based extractor firing on LLM offline, timeout, or malformed JSON (<15ms)                                        |
| Entities surfaced read-only  | Done   | 2026-08-29 | Enriched GET /api/v1/complaints/{id} returning extracted_entities                                                                                 |

## Phase 7 — Integration Hardening & Demo Prep

| Task                                     | Status | Date       | Notes                                                                                                                                                                          |
| ---------------------------------------- | ------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| End-to-end run (no mocks)                | Done   | 2026-08-29 | 55/55 unit & integration tests passing; clean docker-compose stack running with Postgres, Redis, Neo4j                                                                         |
| /check-wallet load test (<200ms p95)     | Done   | 2026-08-29 | 500 requests @ c=25: p95 = 71.25ms (p50 = 23.94ms, p99 = 83.03ms, throughput: 617.8 req/s)                                                                                     |
| Explorer rate-limit burst audit          | Done   | 2026-08-29 | BTC & ETH: 10/10 burst. TRON: 10/10 keyed success with active TRONSCAN_API_KEY (configured in .env)                                                                            |
| VASP attribution field audit             | Done   | 2026-08-29 | Blockscout: confirmed live to.metadata.tags['Bitfinex: Hot Wallet']. Tronscan: KNOWN_VASPS dictionary handles exchange attribution while toAddressTag provides contract labels |
| LLM warm latency stability check         | Done   | 2026-08-29 | 10 repeated warm calls: stable 2.67s–2.69s @ 47.8 tok/s; 2.3GB VRAM static on RTX 2050 (no leaks)                                                                              |
| Unsupported-chain handling               | Done   | 2026-08-29 | GET /wallets/{addr}/trace?chain=BSC returns structured 422 UNSUPPORTED_CHAIN error envelope                                                                                    |
| Security boundary isolation              | Done   | 2026-08-29 | /check-wallet strictly rejects JWTs (401 INVALID_API_KEY); /api/v1/* strictly rejects API keys (401 UNAUTHORIZED)                                                              |
| CORS hardening                           | Done   | 2026-08-29 | Configured CORSMiddleware supporting localhost 3000, 5173, 8000, 8080 and dev regex with credentials                                                                           |
| docker-compose demo-day command verified | Done   | 2026-08-29 | Fixed spacy>=3.7.5 typer conflict in requirements.txt; docker compose up --build brought up all 4 containers healthy (/health: 200 OK)                                         |
| Audit log verified                       | Done   | 2026-08-29 | Direct SQL query verified real rows in audit_log for view_case, update_case_status, and export_pdf_report with investigator actor & timestamps                                 |

---

## Blockers log

| Date       | Blocker                               | Notes                                                                                                                                                                                                                                                                                                                                                                                                                                        | Resolved?                                 |
| ---------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 2026-08-28 | Blockchain Explorer Data Source Audit | Verified that Phase 3 GET /trace uses 100% real live keyless public APIs: BTC uses Blockstream Esplora (blockstream.info/api) & Mempool.space; ETH uses Blockscout v2 REST API (eth.blockscout.com/api/v2). Neither is mocked. Tested and confirmed against live mainnet transactions. Optional Etherscan/Alchemy API keys can be added for higher rate limits.                                                                              | Yes (Verified Keyless Live)               |
| 2026-08-28 | Phase 6 LLM Hardware Feasibility      | Host machine has NVIDIA RTX 2050 (4 GB VRAM) and 12 GB RAM (~2.5 GB free). Llama-3-8B (needs 5.5–6 GB VRAM) cannot fit in 4 GB GPU VRAM alone and is slow/tight on CPU. Ollama is installed at C:\Users\user\AppData\Local\Programs\Ollama. Recommended architecture: Use lightweight 3B local models (Llama-3.2-3B or Qwen2.5-3B) which fit 100% in 4 GB VRAM, with deterministic spaCy / regex fallback for air-gapped low-spec execution. | Documented / Solved via 3B/spaCy fallback |
| 2026-08-29 | Phases 0–5 Codebase Dynamic Audit     | All endpoints (/correlate, /check-wallet, /trace, /risk, /cases/{id}/report) verified dynamic against live Postgres, Redis, Neo4j, Blockstream/Blockscout APIs, and trained XGBoost/SHAP. Found minor Phase 0 leftovers: hardcoded dev credentials in auth.py (line 47), obsolete Phase 0 stub files (risk_model.py, rules.py, clustering.py), and cold-start fallback import name in model.py (line 27).                                    | Documented / Pending cleanup              |

## Contract changes requested

| Date | Endpoint | Change | Agreed with Frontend? |
| ---- | -------- | ------ | --------------------- |
