# ARGUS — System Design Document

**SIH26183 · MHA / I4C · Blockchain & Cybersecurity Track**
*Real-Time Blockchain Intelligence & Crypto Fraud Attribution System*

> This document is written from a direct read of `github.com/UniqCoder/argusx` (frontend
> repo root + `sih-backend/` for the backend) — not from the README's marketing framing
> alone. Where the README/marketing claims differ from what the code and internal audit
> docs (`docs/incidents/`, `GRAPHSAGE_AUDIT_*`, `docs/ml.md`) actually show, this document
> follows the code. That gap is itself documented in §6, because a judge or auditor who
> reads both will find it, and you want to be the one who explained it first.

---

## 1. Problem Statement

**SIH26183**: *"Real-Time Identification of Fraud-Linked Cryptocurrency Exchanges from
Victim-Reported Suspect Wallet Addresses through Automated Blockchain Analytics."*

When a citizen reports crypto fraud (investment scam, ransomware, task-based/"digital
arrest" fraud, sextortion, phishing) via NCRP, the stolen funds are already moving —
through layering wallets, mixers, and cross-chain bridges — toward a cash-out point at
an exchange. Investigators today cannot quickly answer: *which VASP does this wallet
funnel into, and can we freeze it before cash-out?* Argus exists to close that latency
gap between complaint and freeze request.

---

## 2. Product Vision

```
Victim Reports Fraud  →  Argus traces the wallet  →  Follows the fund flow
        ↓                        ↓                          ↓
 Cross-victim correlation   Multi-hop tracing        Risk scoring with
 (NCRP complaint linking)   (BTC / ETH / TRON)        explainable evidence
        ↓                        ↓                          ↓
 Network signal strength    VASP attribution      Court-ready evidence trail
        ↓                        ↓                          ↓
                    💰 Freeze request before cash-out 💰
```

The product is aimed at three personas: the **investigator** (active case work,
wallet tracing, report generation), the **VASP compliance officer** (real-time
deposit-time hold/block signal), and the **compliance viewer** (read-only oversight).

---

## 3. The Three USPs (as defined in the PRD, `docs/unigraph-prd-v2.md §4`)

| # | USP | What it actually is | Build status |
|---|---|---|---|
| **1** | **Cross-Victim Correlation Engine** | Same wallet hitting multiple NCRP complainants across states gets auto-linked — victim count, geographic spread, signal strength (HIGH/MED/LOW) | ✅ Implemented — `correlation_service.py`, `/api/v1/correlate` |
| **2** | **Real-Time Chokepoint at Deposit** | VASP calls `/check-wallet` on every incoming deposit; Redis-only hot path, p95 < 200ms, returns allow/hold/block | ✅ Implemented — `registry_service.py`, `/check-wallet` router, verified live at ~3–6ms avg in testing (see §6) |
| **3** | **100% Data Sovereignty via Local LLM & On-Prem Graph** | FIR/complaint narrative text never leaves the local network; NER via air-gapped Ollama (Llama 3.2 3B) with spaCy fallback; graph stored on-prem in Neo4j, not a third-party API (Chainalysis/TRM/Elliptic excluded by design) | ✅ Implemented, with a documented hardware constraint (see §6) |

This is a genuinely good three-USP pitch: #1 and #2 are concrete, demoable, and
address the actual bottleneck (speed-to-freeze); #3 is a real differentiator against
commercial competitors who'd require sending FIR text to a third-party API.

---

## 4. System Architecture

```
┌───────────────────────────────────────────────────────────────────────────┐
│                         FRONTEND — React 19 + TanStack                     │
│  3D Landing (Three.js/R3F) │ Dashboard │ Investigate │ Evidence & Reports  │
└──────────────────────────────────┬──────────────────────────────────────┬─┘
                                    │ REST (JWT)                          │ API Key
┌───────────────────────────────────▼──────────────────────────────────────▼─┐
│                          BACKEND — FastAPI (Python)                         │
│                                                                              │
│   routers/  (HTTP only)                                                    │
│     auth · complaints · correlate · wallets · cases · alerts · check_wallet │
│                                                                              │
│   services/ (business logic — routers never touch DB/Neo4j directly)       │
│     correlation_service · tracing_service · risk_service · sanctions_service│
│     registry_service · case_service · report_service · osint_service       │
│     alert_service · audit_service · explorers/{btc,eth,tron}               │
│                                                                              │
│   ml/  (65+ modules — see §6.4, this is the most iterated part of the repo)│
│     features · model · explain (SHAP) · train · graph_features ·           │
│     live_graph_features · embedding_store · relative_features · …          │
│                                                                              │
│   graph/        neo4j_client · cypher · known_illicit (hardcoded 2-addr)   │
│   nlp/          llm_ner (Ollama) · spacy_fallback                          │
│   workers/      celery_app · tasks/{alerts,graph_builder,                  │
│                  illicit_enrichment,osint_refresh,registry_refresh}        │
└──────┬─────────────────┬─────────────────┬──────────────────┬─────────────┘
       │                 │                 │                  │
  ┌────▼────┐      ┌─────▼────┐      ┌─────▼─────┐      ┌─────▼──────┐
  │Postgres │      │  Neo4j   │      │   Redis    │      │  Ollama    │
  │(cases,  │      │(wallet/  │      │(risk       │      │(Llama 3.2  │
  │complaints│      │ tx graph)│      │ registry,  │      │ 3B, local) │
  │wallets) │      │          │      │ Celery bus)│      │            │
  └─────────┘      └──────────┘      └────────────┘      └────────────┘
```

**Key architectural invariant already enforced in code** (`rules.md` rule 3,
verified in `check_wallet.py`): `/check-wallet` is **Redis-only** in its hot path.
It calls `registry_service.check_wallet_hot_path()` — never Postgres, never Neo4j,
never the ML model synchronously. This is a genuinely well-built separation and is
one of the strongest engineering decisions in the repo; it's also exactly the
pattern the risk-scoring layering work (§7) needs to preserve.

`evaluate_wallet_risk()` (the full ML + sanctions + graph pipeline) is used **only**
by the investigator-facing `/api/v1/wallets/{address}/risk` endpoint — it is *not*
shared with `/check-wallet`. This matters for §7: the two endpoints already have
independent latency budgets, so async caching decisions for one don't have to be
retrofitted onto the other.

---

## 5. Technology Stack

### Frontend
| Layer | Tech | Notes |
|---|---|---|
| Framework | React 19 | |
| Routing | TanStack Router | file-based, auth guards |
| Data fetching | TanStack Query | |
| Styling | Tailwind CSS 4 | |
| Components | Radix UI | |
| 3D | Three.js + React Three Fiber + Drei | landing page only |
| Animation | GSAP | scroll-driven |
| Charts | Recharts | |
| Forms | React Hook Form + Zod | |
| State | Zustand | |
| Auth | Supabase Auth (JWT) | |

### Backend
| Component | Tech | Notes |
|---|---|---|
| API | FastAPI | auto OpenAPI docs at `/docs`, spec source of truth at `contracts/openapi.yaml` |
| Relational DB | PostgreSQL 15 | cases, complaints, wallets, audit log |
| Graph DB | Neo4j 5 | wallet/tx relationship graph — **no GDS plugin installed**; Cypher-only |
| Cache/Queue | Redis 7 | risk registry (`risk:{chain}:{address}`), Celery broker |
| ML | XGBoost + SHAP | current production model: 92 features (see §6.4) |
| Training data | Elliptic++ (real, 822,942-actor dataset) | see §6.4 for the synthetic-data incident this replaced |
| LLM | Llama 3.2 3B via Ollama | air-gapped, local only |
| NLP fallback | spaCy | deterministic, used when Ollama unavailable |
| Task queue | Celery | async tracing, alerts, enrichment, registry refresh |
| Blockchain APIs | Blockstream/Mempool.space (BTC), Blockscout (ETH), Trongrid (TRON) | keyless public explorers, verified against live mainnet |

### Infra
Docker Compose (dev), Nginx (prod reverse proxy planned), OpenAPI 3.1 contract,
JWT (investigator/admin/compliance-viewer roles) + API-Key auth (VASP chokepoint only).

---

## 6. Honest Current Implementation State

The README's phase table marks Phases 0–7 as "✅ Done." That's true in the sense that
every phase has shipped, working code behind it — but "done" is doing a lot of work in
that table for a system whose ML component has been rebuilt from scratch four times.
Below is what's actually true per phase, drawn from the code and the project's own
incident/audit docs (which is, itself, a point in the project's favor — few hackathon
teams write up their own label-leak post-mortem).

### 6.1 Phase 0–1 — Scaffolding & Cross-Victim Correlation ✅ Solid
Contracts-first (`contracts/openapi.yaml`), FastAPI skeleton, JWT stubs, then real
NCRP complaint ingestion + correlation logic. No known issues.

### 6.2 Phase 2 — Registry + Chokepoint ✅ Solid, verified live
`/check-wallet` benchmarked live: BTC/ETH/TRON sequential-call tests all returned
HTTP 200 at **2.7–6.2ms average latency**, well inside the 200ms p95 target. Redis-only
hot path confirmed in code (§4).

### 6.3 Phase 3 — Multi-Chain Tracing ✅ Solid, verified against real mainnet data
An early blocker (2026-08-28) found the team had almost shipped against a git-clone
failure that silently fell back to something else; it was caught and the explorers
were re-verified against live Blockstream/Mempool.space (BTC) and Blockscout (ETH)
responses — confirmed not mocked.

### 6.4 Phase 4 — ML Risk Scoring — the most instructive part of this repo

This is worth walking through in detail because the *history* is the evidence of
engineering rigor, not the final number alone.

**What actually happened, in order:**

1. **Synthetic-data incident (2026-08-28/29).** The real Elliptic++ dataset failed
   to download (upstream Git LFS quota), so early Phase 4 silently trained on a
   programmatic synthetic approximation of the same 55-column schema. Reported
   metrics at that point (AUC-PR 0.9541 / 0.4883, AUC-ROC 0.9950) are **synthetic
   artifacts** and were retroactively flagged as such in `progress.md`. The team
   found the real dataset via the official Google Drive mirror, downloaded the
   authentic 822,942-actor CSVs, and retrained from scratch with all synthetic
   code paths deleted.

2. **First real-data benchmark**, 49 time-step temporal split (train: steps 1–29,
   validation: 30–34, test: 35–49): **test AUC-PR 0.386**, threshold 0.90,
   test recall 41.5% at FPR 3.6%. A `<1% FPR` target was found **not achievable**
   at usable recall on this dataset (FPR 0.65% only at recall 49.7%).

3. **GraphSAGE embeddings investigated, audited, and found not to help.**
   An internal audit (`GRAPHSAGE_AUDIT_FINDINGS.md`) discovered the original
   "GraphSAGE improves AUC-PR" claim was a **hyperparameter-mismatch artifact** —
   under an identical-hyperparameter fair comparison, GraphSAGE embeddings moved
   AUC-PR from 0.3974 → 0.3827 (**worse**). Despite this, a later promotion
   (2026-09-05) *did* fold 16-dim GraphSAGE embeddings into the production
   92-feature model as part of a broader feature/threshold overhaul — this
   promotion was validated independently (harness-vs-runtime feature equivalence
   exact, OOD false-positive gate 6/6 pass) and is a separate, later decision from
   the original rejected claim. Both are true and both are documented; they are
   not a contradiction once you read the dates.

4. **Simple engineered graph features tried as a GNN alternative**
   (`illicit_neighbor_ratio_1hop/2hop`, `shortest_path_to_known_illicit`) —
   **this is exactly the L2 "graph proximity" layer discussed in this project's
   risk-scoring design work.** Two independent attempts were made:
   - First attempt: raw/processed feature semantic mismatch → no signal.
   - Second attempt: a **self-referential label leak** (2026-09-06) — the
     snapshot builder seeded "known illicit" from the *full* dataset (train+val+test)
     instead of train-only, so every test-split illicit wallet's own gold label
     leaked back in as `shortest_path=0`. This inflated BTC test AUC-PR from an
     honest 0.4665 to a spurious **1.0000**. The leak was caught the same day by
     an internal audit (oracle proof: 4,938/4,938 test-illicit wallets had
     `shortest==0`, 0/90,012 licit wallets did), the leaky model was archived
     (never served live), and production was restored to the pre-leak artifact.
   - **Net finding, written into `docs/incidents/2026-09-06-label-leak.md`:**
     *"Graph features add zero real signal on this dataset's offline metric."*
     The 3 graph feature columns exist in the trained model's 92-feature schema
     but are **constant 0 for BTC rows in the shipped production model** — i.e.
     they are currently dead weight in the classifier, even though a live Neo4j
     query path exists to compute them (`live_graph_features.py`, 2s timeout with
     zero-fallback) for observability/evidence purposes.

5. **Current production model** (`risk_model.joblib`, promoted 2026-09-05):
   **92 features** = 72 tabular/graph (includes the 3 dead graph columns) + 16
   GraphSAGE embeddings + 4 entity-scale-relative features. Locked threshold
   **0.70** (2% FPR policy cap; a 0.85 override achieves <1% FPR at a cost of
   ~8pp recall — both are implemented and documented as an explicit tradeoff).
   Verified metrics: **BTC test AUC-PR 0.4665, ETH test AUC-PR 0.9717**, combined
   test recall 0.420 @ FPR 1.59%. Live false-positive re-check on real deployed
   endpoint: Satoshi Genesis 0.031, Binance cold 0.007, Binance hot 0.061, Vitalik
   0.011, Coinbase ETH 0.007 — all correctly LOW.

**Why this history matters for the design doc:** the README's "Test AUC-PR = 0.954"
is stale/superseded — it's from an earlier iteration (possibly the synthetic-data
run). The **honest, current, production number is BTC AUC-PR 0.4665 / ETH 0.9717**.
This is not a weakness to hide; a temporal-drift-limited AUC-PR of ~0.47 on a
2017–18 BTC dataset applied to 2026 wallets, with a documented and audited reason
why, is a *stronger* story for judges than an unexamined 0.95 would be — it shows
you understand your model's limits and built deterministic guardrails around them
rather than trusting the number blindly. Say this explicitly in the pitch.

### 6.5 Phase 5 — Case Management + Reports ✅ Implemented
State-machine case transitions (`case_service.py`), PDF report generation
(`report_service.py`), 10-section forensic report format per README.

### 6.6 Phase 6 — LLM NER ✅ Implemented, with a documented hardware constraint
Host GPU (RTX 2050, 4GB VRAM) cannot run Llama-3-8B-Instruct at usable latency —
this was caught early (2026-08-28) and the team correctly substituted
**Llama-3.2-3B-Instruct**, which fits fully in 4GB VRAM, with spaCy as a
deterministic fallback. The PRD's own hackathon-day plan (§ "Hours 32–36") notes
the team considered describing LLM NER as "roadmap/architecture" in the pitch
rather than demoing it live if time ran short — worth confirming which path was
actually taken before the pitch, since the pitch narrative should match reality.

### 6.7 Phase 7 — Hardening ✅ Implemented
CORS, audit logging (`audit_service.py`), integration pass. A 2026-08-29 audit
found and fixed leftover Phase-0 stub files and hardcoded dev credentials in
`auth.py` — worth re-confirming these are gone before any public demo/deployment,
since "found and fixed" in an internal doc isn't the same as "verified gone" in
a fresh audit.

---

## 7. Risk Scoring Engine — Architecture (Current State + Design Target)

This is the component under active redesign (this session's work) and deserves its
own section since it's the connective tissue between ML, graph, and deterministic
rules.

### 7.1 The problem this redesign solves
The current `evaluate_wallet_risk()` scores wallets with a single XGBoost pass.
Sanctioned/known-bad wallets don't necessarily *behave* anomalously — sanctions
status is a fact about identity, not a pattern in transaction timing/fees/volume —
so a purely behavioral classifier structurally cannot catch them from behavior alone.
**Good news: this codebase already has a sanctions override in place** (see 7.2) —
the redesign is about making the *other* two signal types (graph association,
behavioral anomaly) equally rigorous and cleanly layered, not about bolting sanctions
detection on for the first time.

### 7.2 Layer 1 — Sanctions/Watchlist (✅ already implemented, migration planned)
`sanctions_service.py` runs **first**, before any DB/explorer/graph/ML work,
inside `evaluate_wallet_risk()`. Current mechanism: curated JSON seed
(`app/data/sanctions_seed.json`, ~133 OFAC SDN addresses, generated by
`scripts/build_sanctions_seed.py`) loaded into an in-memory dict at startup, plus a
best-effort Redis registry consult for operationally-seeded designations. A match
returns a hard override (`risk_score=1.0`, `risk_tier=critical`,
`risk_source=sanctions_override`) — verified live for the Garantex test address.

**Planned migration (per this session's design work):** replace the JSON-seed +
in-memory-dict runtime path with a Postgres `sanctioned_addresses` table as sole
runtime source of truth (columns: address, chain, sdn_entity_name, sdn_program,
list_source, date_added, date_delisted). The JSON file becomes a migration input,
not a runtime path. Redis stays as the hot-path cache, now populated from Postgres.
Rationale: two live sources of truth (JSON + whatever else) can silently drift;
one authoritative table with a documented migration path cannot.

### 7.3 Layer 2 — Graph Proximity (⚠️ exists but currently non-functional)
`live_graph_features.py` computes `illicit_neighbor_ratio_1hop/2hop` and
`shortest_path_to_known_illicit` live from Neo4j on every `/risk` call, with a 2-second
timeout and zero-value fallback. **But per §6.4, these 3 columns are constant 0 in the
currently-deployed model** — they were found to add no real signal after two audited
attempts (including a caught label leak), so effectively **Layer 2 does not
meaningfully influence risk_score today**, despite the live query running on every call.

**Design target (this session's plan):** don't chase GDS Louvain/PageRank yet (real
tuning effort, no labeled data to validate cluster quality against, not worth the time
against a hackathon deadline). Instead:
- Build a **standalone `graph_proximity_service.py`** that turns the existing 3
  Cypher-derived signals into their own 0–1 score, decoupled from XGBoost's feature
  vector — so it can act as an independent decision layer rather than dead weight
  inside a classifier that's already trained to ignore it.
- **Precompute asynchronously via Celery**, cached in Redis with a 6h TTL, refreshed
  on a schedule *and* dispatched by `graph_builder.py` when new edges touch a wallet —
  never computed live inside `/check-wallet`'s hot path (that invariant, §4, must hold).
- `/api/v1/wallets/{address}/risk` (investigator-facing, no tight SLA) can additionally
  support a `force_refresh` param for an on-demand live recompute — since an
  investigator actively working a case benefits from certainty over speed, unlike an
  automated VASP caller.
- Handle cold-start explicitly: a wallet with no cached score yet is `null`
  (not-yet-computed), never silently defaulted to 0 — a 0 must mean "computed and
  genuinely low," not "we haven't looked yet."

### 7.4 Layer 3 — Behavioral (XGBoost) — ✅ production, keep as-is
The 92-feature model from §6.4. Not touched by this redesign — the graph-proximity
work is additive orchestration around it, not a retrain.

### 7.5 Combining the layers
`final_score = max(sanctions_override, graph_proximity_score, behavioral_score)` —
**never a weighted average.** A hard sanctions hit or strong graph-cluster proximity
must not be diluted by a clean-looking behavioral score; averaging would let two
correct "this is bad" signals get pulled down by one legitimately-blind one.
Tie-break attribution order: sanctions > graph > behavioral, surfaced as a
`flagged_by` field.

### 7.6 Endpoint contracts
- **`/check-wallet`** (VASP hot path, p95<200ms, Redis-only): add `risk_tier` +
  `flagged_by` to the existing `{risk_score, action, case_ref}` response. No full
  sub-scores — that's an investigator-transparency need, not an automated-caller one.
  Current schema (`app/schemas/check_wallet.py`) confirmed as the minimal
  3-field shape described above — this is a real, small, low-risk schema addition.
- **`/api/v1/wallets/{address}/risk`** (investigator-facing): full transparency —
  `sanctions_score`, `graph_proximity_score`, `behavioral_score`, `flagged_by`,
  `flagged_by_detail` (sanctions entity/program name; graph cluster/hop distance/
  neighbor ratio; behavioral top-SHAP features), plus existing SHAP evidence.

---

## 8. Known Technical Debt / Open Risks (from the project's own audit trail)

Ranked by what would actually hurt you in front of judges or in production, not by
when they were found:

1. **Enrichment feedback-loop risk (documented, unresolved).** `illicit_enrichment.py`
   sets `Wallet.illicit=true` in Neo4j from two sources: (a) a hardcoded 2-address
   constant — fully independent, safe — and (b) wallets linked to Postgres cases with
   `status=frozen`. Path (b) means: model flags wallet → analyst freezes case (human
   gate) → enrichment marks it illicit → future graph-proximity queries treat it as a
   known-bad neighbor → *future model scores of its neighbors are influenced by a past
   model-adjacent decision.* The human gate prevents runaway drift today (only 2–3
   enriched wallets exist), but there's no provenance check stopping model-derived
   cases from feeding back into the enrichment set as the case volume grows. **Fix is
   cheap now, expensive later — do it before case volume grows**, not after.

2. **Training/serving asymmetry on `shortest_path`.** Training data enforces
   `shortest_path ∈ {1..6}` (self-referencing is explicitly excluded, per the
   label-leak fix); live serving currently allows `{0..6}` for enriched wallets
   (`live_graph_features.py:220`). Not currently harmful (few enriched wallets), but
   undocumented as an explicit exception — should be either enforced or written down
   as a deliberate, reviewed exception before it's forgotten.

3. **No CI/regression guard on the snapshot invariant.** `verify_snapshot.py` (the
   8-address spot-check that catches leaks like §6.4's) is a manual script, not wired
   into any CI, pytest suite, or startup check. A future edit to
   `snapshot_graph_features.py` or `live_graph_features.py` could silently reintroduce
   the exact leak that was already caught once.

4. **Hardcoded dev credentials found in `auth.py`** during the 2026-08-29 audit,
   marked "documented/solved" — worth a fresh grep before any public deployment or
   demo where the repo might be inspected, since "solved" in a progress log isn't
   the same guarantee as a clean `git grep` today.

5. **Known-entity allowlist assessed but not built.** `docs/known_entity_allowlist_feasibility.md`
   is a genuinely useful piece of prior work — it maps candidate sources (OFAC SDN,
   Etherscan labels, exchange cold-wallet announcements, TRONSCAN labels) for a
   deterministic "known-legitimate" override layer to fix the Satoshi-Genesis/
   Ethereum-Foundation-class false-positive problem the ML model has (§6.4 point 5
   shows Satoshi Genesis scoring 0.513/medium on an earlier model iteration purely
   from topological rarity). This is assessment-only; no code exists yet.

6. **README/reality drift.** The public README states "Test AUC-PR = 0.954" and all
   phases uniformly "✅ Done" with no caveats. Both are true of *some* point in the
   project's history but not the current, honest, audited state (§6.4). If this
   README is what judges read first, the actual numbers and the *reason* they're
   lower (temporal drift, honestly measured) should be the pitch talking point, not
   a discrepancy someone else finds first.

---

## 9. What's Remaining — Prioritized Roadmap

### P0 — Correctness & integrity (do before demo)
- [ ] Re-verify no hardcoded credentials remain in `auth.py` (§8.4)
- [ ] Enforce or explicitly document the `shortest_path` live-serving exception (§8.2)
- [ ] Wire `verify_snapshot.py`'s invariant into an automated check (even a pre-commit
      hook or a startup assertion is better than nothing) (§8.3)

### P1 — Risk-scoring layering (this session's design work, concrete next build)
- [ ] Postgres `sanctioned_addresses` table + Alembic migration + seed script from
      existing `sanctions_seed.json` format; remove JSON-seed runtime path (§7.2)
- [ ] `graph_proximity_service.py` — standalone 0–1 score from existing Cypher
      features, decoupled from XGBoost's dead feature columns (§7.3)
- [ ] Celery task + Redis cache-aside for graph proximity (6h TTL, cold-start as
      explicit `null`/not-yet-computed, stale-with-flag rather than blocking) (§7.3)
- [ ] `graph_builder.py` dispatch hook on new-edge ingestion (§7.3)
- [ ] Orchestration function: `max(L1, L2, L3)` with `flagged_by` attribution (§7.5)
- [ ] Schema updates: `CheckWalletResponse` (+`risk_tier`, +`flagged_by`);
      `/risk` response (+ full sub-scores + `flagged_by_detail`) (§7.6)
- [ ] Tests: override precedence, cache-miss fallback, invariant that `/check-wallet`
      never touches Neo4j synchronously (latency test)

### P2 — Model quality / false-positive reduction
- [ ] Build the known-entity allowlist (feasibility already assessed, §8.5) — this is
      probably higher ROI than chasing GDS/GraphSAGE further, since it directly fixes
      a demoable false-positive class (Genesis/Foundation addresses)
- [ ] Enrichment provenance guard (§8.1) — restrict Neo4j `illicit=true` writes to the
      hardcoded-constant source only, or add a check preventing model-derived cases
      from feeding the enrichment set

### P3 — Stretch / explicitly deferred by the team already
- [ ] GDS Louvain/PageRank clustering (PRD lists as v1-target/stretch; this session's
      design work deliberately deferred it — needs labeled data to validate cluster
      quality, real hyperparameter tuning time)
- [ ] Node2Vec/GraphSAGE-based cluster embeddings beyond the current 16-dim static
      embedding lookup
- [ ] Cross-chain bridge event correlation (mentioned in use-cases table, unclear
      if implemented — verify against `tracing_service.py` before claiming it live)
- [ ] Temporal GNN / EvolveGCN (PRD stretch item)

---

## 10. Appendix

### 10.1 API Surface (from `contracts/openapi.yaml` + router inspection)
| Method | Endpoint | Auth | Latency budget |
|---|---|---|---|
| POST | `/api/v1/auth/login` | — | normal |
| POST | `/api/v1/auth/refresh` | JWT | normal |
| GET | `/health` | — | normal |
| POST | `/api/v1/wallets/trace` | JWT | async (Celery) |
| GET | `/api/v1/wallets/{id}/risk` | JWT | seconds (full pipeline) |
| POST | `/api/v1/correlate` | JWT | normal |
| GET/POST | `/api/v1/cases` | JWT | normal |
| GET | `/api/v1/cases/{id}/report` | JWT | async (PDF gen) |
| POST | `/check-wallet` | API Key | **p95 < 200ms, Redis-only** |

### 10.2 Key Module Reference
| Concern | File |
|---|---|
| Sanctions override | `backend/app/services/sanctions_service.py` |
| Redis risk registry | `backend/app/services/registry_service.py` |
| Full risk pipeline | `backend/app/services/risk_service.py` |
| Live graph features | `backend/app/ml/live_graph_features.py` |
| Offline graph features (dead in prod) | `backend/app/ml/graph_features.py`, `snapshot_graph_features.py` |
| Model training | `backend/app/ml/train.py` |
| Feature schema (92f) | `backend/app/ml/features.py` |
| SHAP explainability | `backend/app/ml/explain.py` |
| Async graph rebuild trigger | `backend/app/workers/tasks/graph_builder.py` |
| Illicit-flag enrichment (feedback-loop risk) | `backend/app/workers/tasks/illicit_enrichment.py` |
| Hardcoded known-illicit constants | `backend/app/graph/known_illicit.py` |
| Engineering rules for AI coding agents | `sih-backend/docs/rules.md` |

### 10.3 Source Documents Consulted
`README.md`, `sih-backend/docs/unigraph-prd-v2.md`, `docs/ml.md`, `docs/progress.md`,
`docs/rules.md`, `docs/known_entity_allowlist_feasibility.md`,
`docs/incidents/2026-09-06-label-leak.md`, `IMPLEMENTATION_STATUS_2026_09_01.md`,
`GRAPHSAGE_AUDIT_EXECUTIVE_SUMMARY.md`, and the actual `backend/app/` source tree.

---

*This document reflects the repository state as of the point read for its
preparation. Re-verify §6/§8 line items against current `progress.md` before
relying on them for a live demo or submission — this codebase changes fast and
documents its own changes unusually well, which is worth using.*
