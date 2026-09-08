# Progress Tracker — Argus Backend

**2026-09-07:** **Investigated the live enrichment task's illicit-labeling path and confirmed the Garantex sanctions override is pre-model.** Frontend/backend verification: the sanctions lookup at `risk_service.py:57-66` short-circuits before the model runs — Garantex 1.0 critical comes from the hardcoded `sanctions_service.py:131`, never from ML or graph features. **Enrichment independence verdict (documented in the leak incident):** SOURCE 1 (`KNOWN_ILLICIT_WALLETS`, 2 curated addresses) is fully independent of model output; SOURCE 2 (frozen cases via `_query_case_blocked_addresses`) has a human-mediated feedback path from model scores (analyst sees alert → creates case → freezes → enrichment flags → graph features → future scores). The loop is gated by two manual analyst actions but the data dependency is closed — flagged as an **open risk** in the incident doc. No automated regression guard exists for the enrichment set or the snapshot invariant (offline-only in `verify_snapshot.py`).

**2026-09-06:** **Label leak found and corrected in graph feature snapshot.** `snapshot_graph_features.py` seeded `illicit_t` from the FULL `wallets_classes.csv`, causing every test-split illicit wallet to self-flag `shortest_path=0`. Oracle proof: 4,938/4,938 test illicit had sp==0, 0/90,012 licit. A/B: leaky=1.0, zeroed=0.1057, corrected=0.4574, baseline=0.4665. Graph features add zero real signal. Reverted to pre-graph-fix model (threshold 0.70, BTC AUC-PR 0.4665) — do NOT retrain. Leaky artifact archived as `risk_model.leaky_graph92.joblib`. Snapshot rebuilt (train-split-only seeds + self-exclusion, CSR rewrite). Full incident: `docs/incidents/2026-09-06-label-leak.md`.

**2026-09-05:** **Promoted the validated 92-feature model to production** (replaces the 88f artifact; `docs/ml.md` "Promoted 92f model"). New `relative_features.py` (JSON era reference, harness-equivalent math — exact equal, max|diff|=0.0), `MODEL_FEATURE_COLUMNS`=92 (72 tabular + 4 relative + 16 GraphSAGE), `risk_service.py` uses the full-tabular 92 path with `RISK_FLAG_THRESHOLD=0.70`. Retrained from scratch with the validated config (tuned HPs, spw=1.0, per-chain weights): locked threshold 0.70 (val recall 0.796/FPR 1.60%), test combined P/R/FPR 0.604/0.420/1.59%, BTC AUC-PR 0.4665, ETH AUC-PR 0.9717 — reproduces the offline benchmark. Full test suite **64 passed** (incl. (1,92) shape assertions). Live FP re-check via the actual `/risk` endpoint: Satoshi 0.031, Bitfinex cold 0.066, Binance cold 0.007, Binance hot 0.061, Binance-8 0.226, Vitalik 0.011, Coinbase ETH 0.007 — 7/7 LOW, none ≥0.60, PASS. 88f retired to history; zero-embedding live-coverage caveat carries over to 92f.

**2026-09-05:** Coverage measurement confirms ~0% of fresh live BTC/ETH addresses appear in the wallet graph (0/40 BTC, 0/40 ETH) — pushed 88f GraphSAGE benefit applies to graph-connected addresses only; documented in ml.md. Promoted the 88-feature GraphSAGE model to production (checks passed): persisted `wallet_embeddings.npz` (265,354×16), added `embedding_store.py` (lookup+zero fallback), extended `features.py` (`MODEL_FEATURE_COLUMNS`=88), rewired `risk_service.py` (embedding lookup → 88-col predict), `explain.py` (88-col SHAP), `train.py` (`train_combined_model` trains 88f w/ embedding augmentation, model.py fallback now delegates to it). Retrained `risk_model.joblib` (88 features, threshold 0.92, val FPR 1.41%, combined test P/R 0.556/0.394, BTC AUC-PR 0.427) — reproduces offline benchmark exactly. FP re-check on promoted artifact: Satoshi Genesis 0.831 HIGH (unchanged), ETH Foundation 0.405 MEDIUM (improved). Full test suite 64 passed.
**2026-09-05:** Retrained offline GraphSAGE benchmark (`graphsage_risk.py`) on the `data/processed/` splits, apples-to-apples with production. Fixed edgelist header read bug (`header=0`) and address case mismatch (processed pipeline lowercases BTC addresses; raw edgelist is preserve-case — verified 265,354 labeled BTC addresses map exactly with zero collisions). Verified edgelist fully consistent with deduped wallet set (822,942 addresses, 0 missing either way). Baseline arm (72 features, per-chain sample weights, combined-val threshold 0.90) **exactly reproduces production metrics** (BTC AUC-PR 0.362, precision 0.479, recall 0.300), confirming a fair comparison. 88-feature arm (72 + 16 GraphSAGE embeddings) improves BTC test: AUC-PR 0.362→0.427 (+18.1%), precision 0.479→0.532, recall 0.300→0.380, at threshold 0.92 (val FPR 1.41% < 2% constraint). Combined test recall 0.321→0.393, precision 0.512→0.556. This reverses the 2026-09-01 finding — GraphSAGE DOES help when trained on the same preprocessed features/weights as production. Artifact: `app/ml/artifacts/graphsage_retrained_comparison.json`; details in `GRAPHSAGE_COMPARISON_RESULTS.md`. Pre-promotion checks passed: (1) ETH regression check — no meaningful regression from the 16 null embedding columns (full-ETH AUC-PR 0.9596→0.9571, nonzero-slice 0.9372→0.9330); (2) FP re-check on 88f — Satoshi Genesis unchanged (0.774→0.778 high), ETH Foundation improved/dropped out of high band (0.806→0.405), both stable under embedding jitter. **Coverage measurement**: sampling 40 fresh live BTC + 40 fresh ETH addresses, **0% had membership** in the 265,354-node graph / 822,942-node Elliptic++ / processed ETH set — fresh victim-reported addresses get zero embeddings, so 88f production gains apply to graph-connected addresses only, documented in ml.md "GraphSAGE Pixel Coverage & Production Scope".

**2026-09-04:** Fixed critical inference gap (69→72 features): rewrote `live_graph_features.py` to use `run_query()`, added `graph_features` param to `compute_feature_vector()`, updated `risk_service.py` to inject graph features at call site. Added `DATASET_TO_CANONICAL_RENAME` keyed dict replacing fragile positional `dict(zip())` — fixed `num_txs_as_receiver` naming bug. Applied full-row dedup hardening (347,569 duplicates found). Wrote `preprocess.py` deterministic pipeline: load, rename, dedup, split, weight, output to `data/processed/`. Updated `train.py` to load from preprocessed CSVs. Retrained `risk_model.joblib` on 72 features: 8/8 tests passing, combined test FPR 1.77% (exceeds <1% target), BTC AUC-ROC 0.843, ETH AUC-ROC 0.986 (no leakage found — driven by 68 zero-activity fraud-only test rows). End-to-end inference verified with real BTC/ETH addresses. Investigated false positives on Satoshi Genesis (0.791) and ETH Foundation (0.806): root cause is non-stationary block number features (training max ~448K, live ~900K+) causing OOD routing — inherent limitation, not fixable. Dropping block features tested and degrades performance catastrophically (FPR 1.77%→8.70%). Threshold locked at 0.90 with documented justification. All 6 audit checks completed.
**2026-09-01:** Closed GraphSAGE investigation following methodological audit. The offline benchmark comparison was unfair due to hyperparameter mismatch (control: 250 trees + no scale_pos_weight; baseline: 150 trees + scale_pos_weight). Fair retraining deferred; instead pivoting to simpler engineered graph features (illicit_neighbor_ratio_1hop/2hop, shortest_path_to_known_illicit) computed directly from AddrAddr_edgelist.csv. GraphSAGE code retained as non-production research artifact. Full audit published in GRAPHSAGE_AUDIT_FINDINGS.md.
**2026-08-31:** Renamed the project branding from Unigraph to Argus across the requested documentation, backend metadata, contracts, and infrastructure surfaces. Existing database identifiers remain unchanged for runtime compatibility.
**2026-08-31:** Retrained the risk model with a 62-feature canonical schema, explicit ETH gas/TRON bandwidth-energy fields, corrected `num_txs_as_receiver`, and `scale_pos_weight=18.63`. Held-out precision improved to 0.4224 and F1 to 0.4142; AUC-PR remains 0.3774 and requires chain-native labeled data for further improvement.
**2026-08-31:** Offline GraphSAGE benchmark added in `app/ml/graphsage_risk.py` using the real Elliptic++ graph. On the same 1–29 / 30–34 / 35–49 split, the tabular+embedding model raised test AUC-PR from 0.3495 to 0.4458 and AUC-ROC from 0.8151 to 0.8858, while keeping the live `/risk` contract and SHAP response shape unchanged.
**2026-08-31:** Live GraphSAGE inference is treated as a fallback-only research path because sparse local neighborhoods on live demo addresses are not reliable for a stable embedding. The active serving behavior stays tabular-only unless there is enough graph context to warrant the full embedding mode.
**2026-08-31:** Kaggle Ethereum Fraud Detection Dataset integration is blocked because no raw dataset or Kaggle credentials are available locally. TRON remains heuristic-only with no claim of native labeled training support.

Update this after every work session — status, date, one-line note per task. Status values: `Not started` / `In progress` / `Blocked` / `Done`.

## Phase 0 — Contract & Scaffolding
| Task | Status | Date | Notes |
|---|---|---|---|
| openapi.yaml drafted | Done | 2026-08-28 | OpenAPI 3.0.3 spec for all PRD §11 routes with security schemes & examples |
| entities.md agreed | Done | 2026-08-28 | Closed enums (RiskTier, CaseStatus, AlertAction, etc.) per PRD §8.2 |
| Error envelope defined | Done | 2026-08-28 | Standard error envelope configured on global & validation exception handlers |
| FastAPI scaffold | Done | 2026-08-28 | Layered architecture (core/, api/, schemas/, models/, services/, graph/, ml/, nlp/, workers/) |
| docker-compose skeleton | Done | 2026-08-28 | docker-compose.yml + docker-compose.dev.yml (postgres, neo4j, redis, backend) |
| /health endpoint | Done | 2026-08-28 | GET /health verified returning 200 and service connectivity reports |
| JWT scaffolding | Done | 2026-08-28 | /auth/login and /auth/refresh with token encoding/decoding and protected route guards |

## Phase 1 — Cross-Victim Correlation
| Task | Status | Date | Notes |
|---|---|---|---|
| complaints/complaint_wallets tables + migration | Done | 2026-08-28 | Created Alembic migration 0001_phase1_tables matching entities.md & PRD §9.4 DDL |
| Synthetic NCRP generator | Done | 2026-08-28 | Standalone CLI script planting controlled shared-wallet clusters & single victims |
| Correlation scoring logic | Done | 2026-08-28 | Deterministic scoring curve based on complaint count & distinct geographic spread |
| POST /api/v1/complaints | Done | 2026-08-28 | Complaint ingestion & paginated listing with state/typology filtering |
| POST /api/v1/correlate | Done | 2026-08-28 | Exact wallet matching across complaints, geography aggregation, and total amount |

## Phase 2 — Risk Registry + Chokepoint
| Task | Status | Date | Notes |
|---|---|---|---|
| Redis registry key design | Done | 2026-08-28 | Designed risk:{chain}:{address} schema with allow/hold/block action determination |
| POST /check-wallet | Done | 2026-08-28 | Real-time chokepoint hook with X-API-Key auth, Redis-only hot path, and async Celery alert dispatch |
| Mock VASP client | Done | 2026-08-28 | CLI client (mock_vasp_client.py) for single checks, seeding, and latency load testing |
| alerts table + GET /api/v1/alerts | Done | 2026-08-28 | Alerts ORM table, alert_service, and GET /api/v1/alerts with resolution filtering |
| Celery notify task | Done | 2026-08-28 | Async notify_alert_task off the response path recording alerts in PostgreSQL |

## Phase 3 — Blockchain Tracing
| Task | Status | Date | Notes |
|---|---|---|---|
| BTC explorer integration | Done | 2026-08-28 | Blockstream Esplora REST API integration with UTXO vin/vout parsing |
| ETH explorer integration | Done | 2026-08-28 | Blockscout v2 REST API integration with exchange metadata tag resolution |
| TRON explorer integration | Done | 2026-08-29 | Tronscan REST API integration; TRON-PRO-API-KEY header; live verified on TLa2f... (Binance Hot); rate limit: 15 req/s with key (5 req/s unauthenticated) |
| Neo4j graph builder (Celery) | Done | 2026-08-28 | Async build_graph_task for multi-hop graph population off request path |
| Nearest-VASP Cypher query | Done | 2026-08-28 | Shortest path query (SENT -> RECEIVED_BY -> DEPOSITS_TO) with VASP entity attribution |
| GET /api/v1/wallets/{address}/trace | Done | 2026-08-28 | Multi-hop tracing endpoint returning TraceResponse with nearest VASP discovery |

## Phase 4 — ML Risk Scoring
| Task | Status | Date | Notes |
|---|---|---|---|
| Feature engineering | Done | 2026-08-28 | 55-feature schema matching Elliptic++ Actors Dataset with strict code assertion guard |
| XGBoost baseline trained | Done | 2026-08-28 | 3-way temporal split (train 1-29, val 30-34, test 35-49). Threshold locked at 0.65 on Val (FPR=0.86%), Test AUC-PR=0.9543, Test FPR=0.90% |
| SHAP evidence output | Done | 2026-08-28 | TreeExplainer generating feature_name, contribution magnitude, and direction |
| GET /api/v1/wallets/{address}/risk | Done | 2026-08-28 | Live risk scoring endpoint returning RiskResponse (score, tier, evidence array) |
| Registry-refresh job | Done | 2026-08-28 | Celery task updating risk:{chain}:{address} in Redis for instant hot-path lookup |

## Phase 5 — Case Management + Reports
| Task | Status | Date | Notes |
|---|---|---|---|
| cases/case_wallets tables | Done | 2026-08-28 | Schema matches entities.md CaseStatus enum (new, investigating, escalated_to_vasp, frozen, closed) |
| PATCH /api/v1/cases/{id} | Done | 2026-08-28 | State machine validated transitions with standard error envelope on invalid transition |
| PDF report generation | Done | 2026-08-28 | ReportLab forensic report with Case summary, Phase 4 SHAP evidence, Phase 3 trace, Phase 1 NCRP complaints |
| GET /api/v1/cases/{id}/report | Done | 2026-08-28 | Binary PDF streaming endpoint with Content-Disposition headers |

## Phase 6 — LLM NER (Air-Gapped Llama-3.2-3B + spaCy)
| Task | Status | Date | Notes |
|---|---|---|---|
| Ollama + Llama-3.2-3B setup | Done | 2026-08-29 | 100% GPU offload on RTX 2050 (2.3GB VRAM). Warm throughput: 46.4 tok/s. Cold-start: ~7.8s, Warm-state: ~2.8s–3.2s for ~130-token structured JSON. |
| Structured extraction prompt | Done | 2026-08-29 | JSON extraction pulling suspect names, normalized INR amounts, crypto wallets, dates, and typologies |
| spaCy fallback | Done | 2026-08-29 | Deterministic regex + spaCy rule-based extractor firing on LLM offline, timeout, or malformed JSON (<15ms) |
| Entities surfaced read-only | Done | 2026-08-29 | Enriched GET /api/v1/complaints/{id} returning extracted_entities |

## Phase 7 — Integration Hardening & Demo Prep
| Task | Status | Date | Notes |
|---|---|---|---|
| End-to-end run (no mocks) | Done | 2026-08-29 | 55/55 unit & integration tests passing; clean docker-compose stack running with Postgres, Redis, Neo4j |
| /check-wallet load test (<200ms p95) | Done | 2026-08-29 | 500 requests @ c=25: p95 = 71.25ms (p50 = 23.94ms, p99 = 83.03ms, throughput: 617.8 req/s) |
| Explorer rate-limit burst audit | Done | 2026-08-29 | BTC & ETH: 10/10 burst. TRON: 10/10 keyed success with active TRONSCAN_API_KEY (configured in .env) |
| VASP attribution field audit | Done | 2026-08-29 | Blockscout: confirmed live to.metadata.tags['Bitfinex: Hot Wallet']. Tronscan: KNOWN_VASPS dictionary handles exchange attribution while toAddressTag provides contract labels |
| LLM warm latency stability check | Done | 2026-08-29 | 10 repeated warm calls: stable 2.67s–2.69s @ 47.8 tok/s; 2.3GB VRAM static on RTX 2050 (no leaks) |
| Unsupported-chain handling | Done | 2026-08-29 | GET /wallets/{addr}/trace?chain=BSC and POST /check-wallet (BSC) return structured 422 UNSUPPORTED_CHAIN error envelope |
| Security boundary isolation | Done | 2026-08-29 | /check-wallet strictly rejects JWTs (401 INVALID_API_KEY); /api/v1/* strictly rejects API keys (401 UNAUTHORIZED) |
| CORS hardening | Done | 2026-08-29 | Configured CORSMiddleware supporting localhost 3000, 5173, 8000, 8080 and dev regex with credentials |
| docker-compose demo-day command verified | Done | 2026-08-29 | Fixed spacy>=3.7.5 typer conflict in requirements.txt; docker compose up --build brought up all 4 containers healthy (/health: 200 OK) |
| Audit log verified | Done | 2026-08-29 | Direct SQL query verified real rows in audit_log for view_case, update_case_status, and export_pdf_report with investigator actor & timestamps |

## Phase 8 — Frontend End-to-End Integration
<!-- Note: VITE_VASP_API_KEY is intentionally client-visible since the Alerts simulator panel stands in for a real VASP backend in this demo -- not an oversight, so it doesn't get 'fixed' by someone later without understanding why it's there. -->
| Screen / Feature | Status | Date | Notes |
|---|---|---|---|
| Centralized API client & TypeScript types | Done | 2026-08-29 | Full OpenAPI type sync, JWT Bearer auto-header injection, X-API-Key chokepoint client, standard error envelopes |
| Auth Screen & App Shell | Done | 2026-08-29 | POST /api/v1/auth/login with investigator role, dev credentials quick-fill, and persistent session state |
| Cross-Victim Correlation (Phase 1) | Done | 2026-08-29 | Dynamic multi-state complaint clusters, live POST /api/v1/correlate evaluation, state/typology filtering |
| Deposit Chokepoint & Alerts (Phase 2) | Done | 2026-08-29 | Live GET /api/v1/alerts 6s auto-polling + interactive VASP simulator (<30ms client HTTP, BTC/ETH/TRON/BSC support) |
| Wallet Tracer & ML Risk (Phases 3 & 4) | Done | 2026-08-29 | Live GET /api/v1/wallets/{addr}/trace on BTC/ETH/TRON, dynamic canvas graph, SHAP explainability tags |
| Case Management & PDF Reports (Phase 5) | Done | 2026-08-29 | Kanban drag-and-drop state machine (PATCH /cases/{id}), binary ReportLab PDF stream download |
| NLP Entity Intelligence Modal (Phase 6) | Done | 2026-08-29 | Live GET /api/v1/complaints/{id} modal surfacing suspect names, INR amounts, extracted wallets, and AI summary |
| Production Build Verification | Done | 2026-08-29 | Zero mock imports remaining in UI code; Vite + TypeScript production build succeeded with exit code 0 |

### Integration Verification Audit (6 Mandatory Pre-Requisites)
1. **Measured Client-Side Request Duration for `/check-wallet`**:
   - Measured via live client HTTP fetch over localhost: **2.71ms – 22.01ms** end-to-end (well within the sub-30ms realistic network + processing envelope; raw Redis hot-path lookup is ~0.8ms).
2. **"65B-Compliant" Claim Status**:
   - Audit found no Section 65B digital certificate generation or SHA-256 signature chain-of-custody in `report_service.py`. The claim was **removed** from `Reports.tsx` and replaced with accurate description: "PDF Evidentiary Package: Multi-Page Forensic Dossier (Case summary, SHAP attribution, on-chain trace, linked complaints)".
3. **Multi-Chain POST `/check-wallet` Measurements (3 Chains & Sequential Latency Investigation)**:
   - **BTC Latency Analysis (10 Sequential Calls)**:
     - Call #01: **102.75ms** (One-time cold-start: initial Celery task module loading & `kombu` socket establishment to Redis broker)
     - Calls #02 – #10 (Warm steady-state): **5.02ms – 8.36ms** (Average: **6.89ms**)
     - *Code Path Audit*: Verified identical Redis-only lookup logic across all chains in `registry_service.py` (`check_wallet_hot_path`). Refactored `notify_alert_task` import to module load time.
   - **ETH (10 Sequential Calls)**: Decision **`hold`** | RiskScore: **0.75** | Latency: **4.58ms avg** (Min 3.72ms, Max 6.24ms) | HTTP 200
   - **TRON (10 Sequential Calls)**: Decision **`block`** | RiskScore: **0.88** | Latency: **4.14ms avg** (Min 3.60ms, Max 5.46ms) | HTTP 200
   - **BTC Unflagged**: Decision **`allow`** | RiskScore: **0.0** | Latency: **2.71ms avg** (Min 2.39ms, Max 3.03ms) | HTTP 200
4. **Plant vs. Genesis Address Distinction**:
   - `1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf2` is confirmed as a deliberately planted synthetic test cluster in `generate_synthetic_ncrp.py` (line 58). Verified live returning 6 linked complaints across 6 states (TS, UP, GJ, DL, KA, TN) with ₹17,83,355 total loss.
   - `1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa` is the actual Satoshi Genesis address used for live mainnet Blockstream explorer tracing.
5. **Frontend Build Clean Run**:
   - `npm run build` executed: `tsc && vite build` ➔ transformed 2,804 modules ➔ **0 errors, exit code 0** (built in 5.04s).
6. **Client-Visible VASP API Key Documentation**:
   - Explicitly commented and documented in `docs/progress.md` (line 84) and `frontend/.env.example`.

---

## Blockers log
| Date | Blocker | Notes | Resolved? |
|---|---|---|---|
| 2026-08-28 | Blockchain Explorer Data Source Audit | Verified that Phase 3 GET /trace uses 100% real live keyless public APIs: BTC uses Blockstream Esplora (blockstream.info/api) & Mempool.space; ETH uses Blockscout v2 REST API (eth.blockscout.com/api/v2). Neither is mocked. Tested and confirmed against live mainnet transactions. Optional Etherscan/Alchemy API keys can be added for higher rate limits. | Yes (Verified Keyless Live) |
| 2026-08-28 | Phase 6 LLM Hardware Feasibility | Host machine has NVIDIA RTX 2050 (4 GB VRAM) and 12 GB RAM (~2.5 GB free). Llama-3-8B (needs 5.5–6 GB VRAM) cannot fit in 4 GB GPU VRAM alone and is slow/tight on CPU. Ollama is installed at C:\Users\user\AppData\Local\Programs\Ollama. Recommended architecture: Use lightweight 3B local models (Llama-3.2-3B or Qwen2.5-3B) which fit 100% in 4 GB VRAM, with deterministic spaCy / regex fallback for air-gapped low-spec execution. | Documented / Solved via 3B/spaCy fallback |
| 2026-08-29 | Phases 0–5 Codebase Dynamic Audit | All endpoints (/correlate, /check-wallet, /trace, /risk, /cases/{id}/report) verified dynamic against live Postgres, Redis, Neo4j, Blockstream/Blockscout APIs, and trained XGBoost/SHAP. Found minor Phase 0 leftovers: hardcoded dev credentials in auth.py (line 47), obsolete Phase 0 stub files (risk_model.py, rules.py, clustering.py), and cold-start fallback import name in model.py (line 27). | Documented / Solved |
| 2026-08-29 | Constant 99.5% ML Risk Score Investigation & Fix | Investigated GET /wallets/{address}/risk returning 0.995 for all inputs. Identified root cause: features.py hardcoded first_block=799000 and lifetime=1000 instead of computing dynamically from tx timestamps, causing extreme out-of-distribution leaf routing in XGBoost. Refactored features.py with dynamic timestamp-to-block height calculations, retrained model with realistic overlap, sanitized MAX_UINT256 smart contract approvals in TronExplorer, and added TRON support to risk_service.py. | Yes (Fixed & Verified Live) |
| 2026-08-29 | Incident: Synthetic Training Data Invalidation & Google Drive Resolution | Logged incident: Git LFS clone failed due to upstream GitHub bandwidth quota on github.com/git-disl/EllipticPlusPlus, causing earlier Phase 4 work to run against synthetic data. Resolved by downloading the real raw 822K-actor dataset from the official Google Drive distribution into data/raw/ellipticpp/ (wallets_features.csv 578MB, wallets_classes.csv 29MB). Rewrote train.py to read directly from disk with all synthetic fallback paths deleted. Retrained and re-evaluated model across all 49 time steps. | Yes (Resolved & Retrained on Real Data) |

### Incident Log: Synthetic Training Data Invalidation & Resolution (2026-08-28 – 2026-08-29)
- **Incident Summary**: Initial Phase 4 implementation used programmatic synthetic data generators (`generate_realistic_elliptic_dataset`) simulating the 55-column Elliptic++ schema. Prior reported metrics (e.g. 0.9541 / 0.4883 AUC-PR, 0.9950 AUC-ROC) were evaluated against synthetic distributions and are formally marked as synthetic artifacts.
- **Root Cause**: An initial `git clone` of `github.com/git-disl/EllipticPlusPlus` failed due to Git LFS bandwidth exhaustion on the upstream repository (`batch response: This repository exceeded its LFS budget`).
- **Resolution**: Located the official Google Drive distribution link from the repository README (`1MRPXz79Lu_JGLlJ21MDfML44dKN9R08l`) and downloaded the authentic 822,942-actor CSV files (`wallets_features.csv` - 578.37 MB, `wallets_classes.csv` - 29.01 MB) into `data/raw/ellipticpp/`. Rewrote `app/ml/train.py` to load directly via `pandas.read_csv` and eliminated all synthetic generator code paths.

### Phase 4 Formal ML Benchmark on Real Elliptic++ Actors Dataset
- **Raw Dataset**: 1,268,260 temporal feature rows ➔ 822,942 unique wallet addresses across 49 time steps. Filtered to 265,354 labeled actors (14,266 illicit Class 1, 251,088 licit Class 2).
- **Temporal Partitions**:
  - **Train Set (Time steps 1..29)**: $N=148,038$ actors ($7,542$ illicit, Base Rate: $5.09\%$)
  - **Validation Slice (Time steps 30..34)**: $N=22,366$ actors ($1,786$ illicit, Base Rate: $7.99\%$)
  - **Test Set (Time steps 35..49)**: $N=94,950$ actors ($4,938$ illicit, Base Rate: $5.20\%$)
- **Validation Slice Threshold Selection**:
  - Scanned candidate thresholds $[0.50 \dots 0.95]$.
  - **FPR Target Finding**: The `<1.0%` FPR target is **not achievable at usable recall** on real Elliptic++ data (at threshold $0.95$, FPR is $0.65\%$ but Recall collapses to $49.66\%$). Threshold **`0.90`** was selected as the best available operational trade-off (**Validation FPR: `1.55%`**, **Validation Recall: `65.40%`**; Test Holdout FPR: `3.60%`, Test Recall: `41.54%`).
- **Out-of-Sample Holdout Evaluation on Test Set (Time steps 35..49)**:
  - **1. AUC-PR (Primary)**: **`0.3862`** (Validation: `0.7223`)
  - **2. Precision @ 0.90**: **`0.3874`** ($TP=2,051, FP=3,243$)
  - **   Recall @ 0.90**: **`0.4154`** ($FN=2,887$)
  - **3. FPR @ 0.90**: **`0.0360`** ($3.60\%$)
  - **4. AUC-ROC (Secondary)**: **`0.8451`** (Validation: `0.9301`)
  - **5. Brier Score**: **`0.1784`** (Validation: `0.1507`)

### Multi-Chain Live Risk Verification & Known Model Limitations
- **Live Test Address Scores (Real Elliptic++ Model)**:
  - **Garantex OFAC Sanctioned (`3Lpoy53...` BTC)**: Risk Score **`0.488` (48.8%)** | Tier: `medium` (SHAP: `fees_as_share_max: +0.6362`, `num_txs_as_sender: +0.2814`)
  - **Binance Cold Storage (`34xp4v...` BTC)**: Risk Score **`0.367` (36.7%)** | Tier: `medium` (SHAP: `transacted_w_address_total: -1.2877`)
  - **Satoshi Genesis (`1A1zP1...` BTC)**: Risk Score **`0.513` (51.3%)** | Tier: `medium` (SHAP: `transacted_w_address_total: -1.1393`)
  - **Bitfinex Cold Storage (`0x742d...` ETH)**: Risk Score **`0.038` (3.8%)** | Tier: `low` (SHAP: `fees_min: -1.5158`, `btc_transacted_mean: -0.6176`)
  - **Binance Hot Wallet (`TLa2f6...` TRON)**: Risk Score **`0.030` (3.0%)** | Tier: `low` (SHAP: `fees_min: -1.0134`, `transacted_w_address_total: -0.6360`)

- **Documented Model Limitations & Defense-in-Depth Architecture**:
  1. **Historical Temporal Window Drift**: Elliptic++ covers a fixed historical Bitcoin time window (time steps 1..49, ~2017–2018). Live, present-day wallet behavior in 2024–2026 differs significantly in fee dynamics, layer-2 interactions, and transaction structures. This temporal drift explains why a real modern sanctioned exchange address (Garantex, score `0.488`) scored lower on pure topological ML than a historically unique edge case (Satoshi Genesis, score `0.513`).
  2. **Mitigating Architecture (Defense-in-Depth)**: Pure topological ML scoring is designed to detect structural anomalies on unflagged/novel addresses. Known-bad addresses, OFAC sanctions, and NCRP-reported victim clusters are intercepted deterministically at the Phase 2 Redis Risk Registry (`/check-wallet`) and Phase 1 victim correlation layer (`/correlate`), guaranteeing hard blocks (`1.00` risk / `block` decision) regardless of the ML score.
  3. **Multi-Chain Semantic Proxy**: Elliptic++ features are Bitcoin UTXO-denominated (`btc_*`). Mapping account-based EVM/TRON transactions into these fields serves as a cross-chain topological proxy; production deployment requires chain-native feature extractors.

## Contract changes requested
| Date | Endpoint | Change | Agreed with Frontend? |
|---|---|---|---|
