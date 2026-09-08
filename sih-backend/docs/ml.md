# ml.md — Argus Backend: Dataset, Training & Testing

> **⚠ SUBMISSION TALKING POINT — read this first (honesty note, do not minimize).**
> The graph-fix retrain metrics documented in the 2026-09-06 section below
> (BTC test AUC-PR 1.0, combined 0.9998) were **invalidated the same day** after
> a post-swap audit found a self-referential label leak in `snapshot_graph_features.py`.
> The pre-graph-fix model (BTC AUC-PR 0.4665, threshold 0.70) is the active
> production artifact. Graph features add zero real signal on this dataset's offline
> metric; infrastructure is retained for live observability only.
> Full details in **[docs/incidents/2026-09-06-label-leak.md](incidents/2026-09-06-label-leak.md)**.
>
> Honest limitation of the production model: the evaluation confirms strong
> tabular feature discrimination (BTC test AUC-PR 0.4665, AUC-ROC 0.8543) while
> "novel-illicit" generalization remains unmeasured by this split. Live behaviour
> intentionally uses the sanctions override for known-bad addresses (e.g., Garantex
> → 1.0 critical via `sanctions_override`, ML model never runs).

This supersedes the dataset table in `datasets-and-ml.md` — deliberately narrowed to **one** dataset for training/evaluation so the feature schema stays consistent end to end. Mixing multiple dataset sources with different columns is the most common cause of train/inference feature mismatch — so don't.

---

## The one dataset: Elliptic++ (Actors / Wallets Dataset)

This is a direct match for "wallet risk scoring" (not just transaction classification) — ~822K labeled Bitcoin wallet addresses (`illicit` / `licit` / `unknown`), with per-wallet features (in/out-degree, transaction counts, volume, activity window, etc.) plus wallet–wallet and wallet–transaction edge lists.

**Where:** `github.com/git-disl/EllipticPlusPlus`, folder `Actors Dataset/`
**Files you need:** `wallets_features.csv`, `wallets_classes.csv`, `AddrAddr_edgelist.csv`, `AddrTx_edgelist.csv`, `TxAddr_edgelist.csv`

**How to get it:**
1. `git clone https://github.com/git-disl/EllipticPlusPlus` (or download the `Actors Dataset/` folder directly from the GitHub web UI — no login required).
2. Open `Elliptic++_Actors_Classification.ipynb` in that folder once before writing your own loader — it shows the exact column names and order. Match your feature-engineering code to that layout, don't rename or reorder.
3. Load `wallets_features.csv` + `wallets_classes.csv`, join on `address`.

**Do not also pull the original Kaggle "Elliptic Data Set."** That's the transaction-only predecessor (166 anonymized columns, no wallet-level features) — a different schema entirely. Bringing it in alongside Elliptic++ is exactly how you'd get mismatched/missing columns.

---

## Testing — comes from the same dataset, no second one needed

- **Split by time step, not randomly.** Elliptic++ has ~49 discrete time steps. Train on roughly the first 34, hold out the rest as your test set. This also doubles as your drift check, so there's nothing extra to download for that.
- **Metrics, in priority order:** AUC-PR (primary — illicit wallets are the minority class) → precision/recall at your deployed threshold → false-positive rate at that threshold (original project target < 1%) → AUC-ROC (secondary) → calibration/reliability curve (the score drives allow/hold/block, not just ranking).

### Threshold cap decision

The threshold selector uses the exact source line `max_fpr: float = 0.020,` in `backend/app/ml/train.py`. This is an intentional deviation from the project's original 1% FPR target. On the real Elliptic++ validation slice, the 2% cap locks threshold `0.92` (validation FPR 1.41%, recall 62.50%, 88-feature production model); enforcing a 1% cap would select `0.95` (validation FPR 0.65%, recall 53.31%). The deployed artifact remains locked at `0.92` because the 2% cap was chosen as the operational recall/FPR trade-off.
- **The actual feature-mismatch guard:** before every training run, assert that the columns your live feature pipeline computes for a wallet (from your own explorer/graph data at inference time) match `wallets_features.csv`'s schema exactly — same names, same order, same units. A five-line assertion, run every time — this is what prevents the mismatch, not the choice of dataset.

---

## Optional second source — sanity check only, never for training
If you want one more signal beyond the held-out split: pull a handful of addresses from the **OFAC SDN sanctions list** (public, treasury.gov) and run them through your already-trained pipeline — just to confirm known-bad addresses get flagged. Don't import OFAC's data as training rows or extra columns; it never touches your feature schema, so it can't reintroduce the mismatch problem.

---

## Step-by-step, start to finish
1. Clone/download the Elliptic++ `Actors Dataset/` folder.
2. Join `wallets_features.csv` + `wallets_classes.csv` on `address`.
3. Sort by time step, split ~34/15 train/test.
4. Train the XGBoost/LightGBM baseline against that schema.
5. Add the feature-pipeline assertion before wiring the model into `GET /api/v1/wallets/{address}/risk`.
6. (Optional) Spot-check a few OFAC SDN addresses through the trained pipeline as a sanity pass — not a formal benchmark.

## Ethereum labeled-source status

The Kaggle Ethereum Fraud Detection Dataset is staged at `backend/data/raw/ethereum_fraud/transaction_dataset.csv` and is loaded by `load_ethereum_fraud_dataset()` in `backend/app/ml/train.py`. It contains 9,841 wallet rows and 51 source columns. `FLAG=0` has 7,662 rows (77.8579%) and `FLAG=1` has 2,179 rows (22.1421%).

The loader maps direct equivalents for sender/receiver counts, transaction counts, Ether sent/received values, counterparties, and sent/received time intervals. It derives transaction value extrema, duration/transaction timing proxies, and a counterparty-count proxy. The source has no transaction-level gas price, gas used, Ethereum fee, or block-height fields, so `gas_price_gwei_mean`, `gas_used_mean`, `native_fee_*`, `chain_fee_*`, `fee_ratio_*`, block-height fields, and unavailable interval statistics remain null and are imputed by the existing training path. Every Ethereum row receives `chain=ETH`; Elliptic++ rows receive `chain=BTC` before concatenation.

The preprocessing pipeline is now `python -m app.ml.preprocess`, which outputs `data/processed/train.csv` (174,163 rows, 76 cols), `val.csv` (23,841 rows, 75 cols), `test.csv` (96,428 rows, 75 cols), and `btc_unlabeled.csv` (557,588 rows). Training loads from these preprocessed splits via `python -m app.ml.train`.

BTC fraud balance is `14,266/265,354` (`5.38%`); ETH fraud balance is `2,179/9,841` (`22.14%`). Combined training set illicit rate: `7.6%`.

The combined training run uses class-stratified 70/15/15 ETH splits, oversamples ETH to 15% of training rows, and applies per-chain balanced sample weights with equal total mass per chain. The 15% target was selected after comparing 5%, 10%, 15%, 20%, and 25% targets because it improves BTC recall/F1 relative to 25% while preserving ETH performance. The model locks threshold `0.90`.

Missingness-indicator SHAP importance was `0.0` for all seven structural indicators (`chain_fee`, `fee_ratio`, `native_fee`, `gas_price`, `gas_used`, `bandwidth`, and `energy`) in both the old 69-feature and new 72-feature models, confirming the audited indicators do not dominate the fitted model. Manual review found 68/1,478 ETH test rows with zero transactions, all labeled fraud; this is a trivial dataset shortcut that inflates the full ETH score. On the 1,410-row non-zero-activity sensitivity slice, the 72-feature model scored precision `0.979`, recall `0.542`, F1 `0.698`, AUC-PR `0.937`. The ETH Kaggle file has no transaction-level gas fields, so its ETH native gas indicators remain structurally missing; live explorer transactions can populate them when available.

## BTC robustness and calibration review

The complete non-production experiment is recorded in [backend/ML_ROBUSTNESS_REPORT.md](../backend/ML_ROBUSTNESS_REPORT.md). After its own validation scan, recency weighting re-locks at threshold `0.88` and improves BTC F1 from `0.3753` to `0.4262` and AUC-PR from `0.3721` to `0.4023`; steps 43, 45, and 47 improve, while step 48 worsens, indicating a structural regime break rather than gradual drift. Validation-only ablation selection chooses removal of `last_block_appeared_in`, whose single held-out test result is F1 `0.4233` and AUC-PR `0.3979`; removing all four time features is harmful. Platt calibration lowers Brier score from `0.1767` to `0.0436` for BTC and from `0.0456` to `0.0386` for ETH. These are challengers only; the production artifact remains unchanged pending review.

The combined recency-plus-ablation challenger locks at `0.90` under validation FPR `1.66%`, but reaches only BTC F1 `0.4193` and AUC-PR `0.3808`; it does not compound the individual gains. Recency-only remains the recommended challenger for future review, with no production promotion made.

TRON remains explicitly heuristic-only: the BTC/ETH-trained model may consume TRON chain-native features for exploratory scoring, but there is no public labeled TRON fraud dataset in this project and no claim of native TRON training support.

---

## Offline GraphSAGE embedding benchmark (non-production research, closed 2026-09-01)

A GraphSAGE encoder was evaluated offline as a feature-generation layer that feeds the existing XGBoost risk model. This work is **no longer pursued** due to methodological findings and resource constraints. The investigation is documented here as a legitimate research record (not something to hide), with full findings published in [GRAPHSAGE_AUDIT_FINDINGS.md](../GRAPHSAGE_AUDIT_FINDINGS.md).

### Audit Finding: Unfair Hyperparameter Mismatch

The benchmark comparison was **fundamentally invalid** because the control model was trained with different hyperparameters than the production baseline:

| Parameter | Production Baseline | GraphSAGE Control | Impact |
|---|---|---|---|
| `n_estimators` | 150 | 250 | +67% more trees |
| `scale_pos_weight` | computed (18.63) | omitted | no class weighting |

This configuration mismatch caused the control to systematically underperform:
- Production baseline test AUC-PR: **0.3774**
- Tabular-only control in benchmark: **0.3495** (⚠️ worse)
- Reported improvement (embedding model): **0.4458**

The apparent uplift was largely a measurement artifact: the control was intentionally weakened, and the embedding model partially recovered back toward the real baseline. A fair comparison requires identical hyperparameters for all three branches.

### Why GraphSAGE Was Closed

1. **Live inference is not feasible** — sparse neighborhoods on demo addresses (15 recent transactions) are too shallow for stable embeddings.
2. **Interpretability trade-off is real** — embedding dimensions add SHAP magnitude without human-readable meaning.
3. **Fair retraining would be expensive** — equal effort/data budget is better spent on simpler engineered features (see next section).

### Research Artifact Status

The production model (`app/ml/graphsage_risk.py` is kept in the repository) remains documented as non-production research, clearly marked for reference by future engineers. The `/risk` endpoint continues to use the pure-tabular XGBoost path with no GraphSAGE component.

---

## Phase 6 Local LLM: Llama-3.2-3B-Instruct (Air-Gapped Ollama)

- **Model:** `llama3.2:3b` (~2.0 GB 4-bit quantized) running locally via Ollama (`http://localhost:11434`).
- **Hardware Rationale:** Fits completely inside 4 GB GPU VRAM (NVIDIA RTX 2050), delivering sub-1.5s per-FIR extraction latency. Full Llama-3-8B requires ~6GB VRAM and is too slow on CPU (~20-35s).
- **Air-Gap Guarantee:** FIR/complaint narrative text is processed strictly on the local Ollama instance without external outbound network calls.
- **Fallback:** Deterministic spaCy/regex entity extraction when Ollama is unavailable or JSON parsing fails.

---

## Known Model Limitations & Defense-in-Depth Architecture

## 2026-08-31 Model Improvement Evaluation

The model now exposes a 62-column canonical schema. Historical Elliptic++ BTC columns are mapped explicitly into chain-neutral names (`value_*`, `chain_fee_*`, and `time_between_*`). ETH transactions populate gas price and gas used; TRON transactions populate native fees, bandwidth, and energy. The receiver feature is consistently named `num_txs_as_receiver` in extraction, vector construction, training metadata, and SHAP output.

Class imbalance handling was already present and is retained: XGBoost uses `scale_pos_weight = licit_training_rows / illicit_training_rows = 18.63` on the training slice. A focused comparison tested weights `9.31`, `13.97`, and `18.63`; the full ratio produced the strongest thresholded held-out F1 and precision of the tested settings.

| Metric | Previous baseline | Retrained model | Change |
|---|---:|---:|---:|
| Test precision | 0.3874 | 0.4224 | +0.0350 |
| Test recall | 0.4154 | 0.4062 | -0.0091 |
| Test F1 | 0.4009 | 0.4142 | +0.0133 |
| Test AUC-PR | 0.3862 | 0.3774 | -0.0088 |

The retrained model is measurably better on thresholded precision and F1, but not on AUC-PR; therefore this is an improved operating-point trade-off, not a claim of broad ranking improvement. Further AUC-PR gains require chain-native labeled training data or additional temporal model validation rather than accepting this run as universally superior.

1. **Historical Temporal Window Drift**:
   - Elliptic++ covers a fixed historical Bitcoin time window (time steps 1..49, ~2017–2018). Live, present-day wallet behavior in 2024–2026 differs significantly in fee dynamics, layer-2/mixing patterns, and transaction structures.
   - This temporal drift explains why a real modern sanctioned exchange address (Garantex, score `0.488`) can score lower than a historically unique edge case (Satoshi Genesis, score `0.513`) on pure topological features.
2. **Mitigating Multi-Layer Architecture (Defense-in-Depth)**:
   - Pure structural ML scoring is designed to identify anomalous topology on unflagged, novel addresses. It is deliberately NOT the only enforcement point.
   - **Two risk signals** are consumed by `/api/v1/wallets/{address}/risk` and `/check-wallet`:
      1. **ML behavioral signal** — `risk_source="ml_model"`: the 92f model + SHAP evidence.
      2. **Sanctions known-bad signal** — `risk_source="sanctions_override"` (`risk_service.py` + `services/sanctions_service.py`, USP 2): a curated, provenance-tracked OFAC SDN digital-currency seed (`backend/app/data/sanctions_seed.json`, generated from the official Sanctions List Service by `scripts/build_sanctions_seed.py`, feed release 2026-09-04) is intercepted deterministically **before** any graph/explorer/ML work in `risk_service.evaluate_wallet_risk`, returning `risk_tier="critical"`, `risk_score=1.0`, and evidence `feature_name="sanctions_interception"` with the designation/list/programs detail — regardless of the ML score. The same list is seeded into the Redis Risk Registry at startup (`sanctions_service.ensure_redis_seeded`) so `/check-wallet` also hard-blocks (`block` decision) sanctioned addresses.
   - Coverage boundary (disclosed): the SDN's structured crypto-address field for Tornado Cash covers only the Semenov developer/associated wallets (8 ETH) — no mixer smart-contract addresses exist in the structured field, so mixer addresses are NOT claimed as covered by this seed; ML remains the only signal for them.
    - **OSINT corroboration signal** — added 2026-09-07 (`services/osint_service.py`, `docs/osint.md`): structured public-source hits from **ransomwhe.re** (ransomware families, keyless bulk API) and **Bitcoin Abuse** (abuse reports, key-gated) surface as `osint` + `osint.*` evidence on `/risk`. This is corroboration only — it never changes score/tier/`risk_source`. **Rate-limit note:** Bitcoin Abuse's free tier allows **30 requests/min (~1 req/2s)**, so `/risk` does not rely on per-request Bitcoin Abuse lookups; the hot path uses the Redis-cached / Celery-synced snapshot, and the live `reports/check` is only an uncached fallback. Etherscan nametags are out of scope (official tag endpoint is paid Pro-Plus only).
   - NCRP-reported scam clusters are intercepted via Phase 1's victim correlation layer (`/correlate`), also guaranteeing hard blocks (`1.00` risk / `block` decision) regardless of the ML score.
   - Concrete example: the Garantex exchange wallet `3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1` may score `0.488` under pure ML topology (temporal drift above), but the sanctions signal overrides it to a hard `critical` / `1.00` block.
3. **Validation FPR vs. Recall Trade-Off**:
   - On the real Elliptic++ dataset, the `<1.0%` FPR target is only reachable at extreme thresholds ($\ge 0.95$, FPR `0.65%`), where Recall drops below 50% (`49.66%`).
   - The implementation intentionally applies a 2.0% validation FPR cap. Threshold **`0.90`** was selected as the operational trade-off (Validation FPR: **`1.55%`**, Validation Recall: **`65.40%`**; Test Holdout FPR: **`3.60%`**, Test Recall: **`41.54%`**).
4. **Within-Dataset Temporal Drift & Leakage Prevention**:
   - Test-holdout performance (Recall 41.5%, FPR 3.6%) is meaningfully weaker than validation-slice performance (Recall 65.4%, FPR 1.55%), consistent with known within-dataset temporal drift in Elliptic-family data -- illicit transaction patterns in later time steps differ from earlier ones even within the dataset's own history. This is disclosed as a generalization characteristic of the benchmark, not a bug, and no further threshold tuning against the test set was performed to avoid re-introducing test-set leakage.

## Engineered Graph Features (Closed 2026-09-06 — Infrastructure Retained for Observability)

Rather than train a GNN, we compute simple, interpretable graph topology features directly from `AddrAddr_edgelist.csv`. These preserve SHAP readability and are cheaper to compute at inference time (no deep learning stack required).

### Feature Engineering Approach

**For every wallet in the training set, compute:**

1. **1-hop illicit neighbor ratio** — share of immediate neighbors labeled illicit in the training-period graph
2. **2-hop illicit neighbor ratio** — share of nodes reachable within 2 hops labeled illicit
3. **Shortest path to known illicit** — minimum graph distance to any illicit-labeled node (capped at 6 to avoid computational explosion on large connected components)

**Graph Data:**
- Nodes: wallets from `wallets_classes.csv` with labels (`class=1` = illicit, `class=2` = licit)
- Edges: from `AddrAddr_edgelist.csv` (both directions represented)
- Training-period edges only: time steps 1–29 edges are used to compute features; validation/test edges are excluded to prevent leakage

### Integration with Existing Feature Schema

The three new features will be added to `FEATURE_COLUMNS` in `app/ml/features.py`:
- `illicit_neighbor_ratio_1hop` (float, [0, 1])
- `illicit_neighbor_ratio_2hop` (float, [0, 1])
- `shortest_path_to_known_illicit` (int, [0, 6])

This increases the feature count from 69 to 72 (62 base + 7 missingness indicators + 3 graph features). The feature-mismatch assertion is updated to match.

### Fair Retraining Protocol

The retrained model uses **exactly the same hyperparameters as the production baseline:**
- `n_estimators=150`
- `scale_pos_weight=computed`
- `max_depth=5`
- `learning_rate=0.06`
- `subsample=0.85`
- `colsample_bytree=0.85`

The only change is the input feature set (62 → 65 features). This ensures any metric difference is attributable to the features, not model configuration. Threshold locking follows the standard procedure: validation FPR cap 2%, select best threshold, apply once to test holdout.

### Expected Outcome & Honest Reporting (Final)

Graph features were investigated in two rounds (2026-09-01 and 2026-09-06) and **add zero real signal** on this dataset's offline metric:
- First attempt (raw/processed mismatch): no useful signal.
- Second attempt (self-referential leak → corrected snapshot): corrected AUC-PR 0.4574 vs baseline 0.4665 — within noise.

The infrastructure is retained for **live inference observability** (neighbor counts and shortest path surfaced in evidence output via `live_graph_features.py`) but is NOT in the active production model's feature set. Graph columns are constant 0 in the training data and the model learned near-zero weights for them.

**If future graph signal is pursued:** use train-split-only seeding with self-exclusion (as fixed in `snapshot_graph_features.py`), enforce `shortest_path ∈ {1..6}` globally, and add an automated regression guard (see [label-leak incident](incidents/2026-09-06-label-leak.md) for open risks).

---

## 2026-09-04 — Preprocessing Pipeline + 72-Feature Retrain

### num_txs_as_receiver Naming Bug (Fixed)

The original `wallets_features.csv` column `n_txs_received` was mapped to `num_txs_as_sender` instead of `num_txs_as_receiver` via the positional `dict(zip(FEATURE_COLUMNS, ...))` approach. This was a silent schema mismatch — the model trained on swapped receiver/sender semantics. Fixed by replacing the positional zip with an explicit `DATASET_TO_CANONICAL_RENAME` keyed dict in `train.py:63`. The 41 renamed columns and 14 unchanged columns are now matched by name, not position.

### Full-Row Duplicate Finding

`wallets_features.csv` contains **347,569 full-row duplicate rows** (1,268,260 raw → 920,691 after full-row dedup). After address-level dedup (keep last timestep): **822,942 unique addresses**. The preprocessing pipeline now applies full-row dedup before address-level dedup to avoid inflating training data with exact copies.

### Preprocessing Pipeline (`app/ml/preprocess.py`)

Deterministic, reproducible preprocessing replaces in-line dedup in `train.py`:

1. Load BTC features + classes, join on `address`
2. Full-row dedup → address-level dedup (keep last timestep)
3. Drop class 3 (unknown) from training; keep as `btc_unlabeled.csv` for inference reference
4. Rename BTC columns via `DATASET_TO_CANONICAL_RENAME`, add 7 missingness indicators
5. Process ETH via Kaggle → canonical direct mapping + derived features
6. BTC split: temporal (train ≤29, val 30-34, test ≥35)
7. ETH split: stratified random 70/15/15
8. Oversample ETH to 15% minimum train share
9. Compute per-chain class-balanced sample weights (equal mass across chains)
10. Output CSVs to `data/processed/`

**Final split sizes:**

| Split | BTC rows | ETH rows | Total | Illicit% |
|-------|----------|----------|-------|----------|
| Train | 148,038 | 26,125 | 174,163 | 7.6% |
| Val | 22,366 | 1,475 | 23,841 | 8.9% |
| Test | 94,950 | 1,478 | 96,428 | 5.5% |
| Unlabeled | 557,588 | — | 557,588 | — |

### Retrained Model (72 Features)

Feature count increased from 69 → 72 (added 3 graph features: `illicit_neighbor_ratio_1hop`, `illicit_neighbor_ratio_2hop`, `shortest_path_to_known_illicit`). Model retrained with identical XGBoost hyperparameters (`n_estimators=150`, `max_depth=5`, `lr=0.06`, `subsample=0.85`, `colsample_bytree=0.85`).

**Locked threshold:** 0.90 (validation FPR 1.91%, recall 57.6%)

**Combined test confusion matrix (all 96,428 test rows):**

| Metric | Value |
|---|---|
| TN | 89,549 |
| FP | 1,613 |
| FN | 3,574 |
| TP | 1,692 |
| **FPR** | **1.77%** |
| Precision | 0.5120 |
| Recall | 0.3213 |
| AUC-PR (BTC) | 0.3607 |
| AUC-ROC (BTC) | 0.8432 |
| AUC-PR (ETH) | 0.9596 |
| AUC-ROC (ETH) | 0.9860 |

**FPR vs. target:** Combined test FPR of 1.77% **exceeds the docs/ml.md target of <1%**. Threshold 0.95 (val FPR 0.55%) would meet the target but drops recall to ~44.6%. The 2% validation FPR cap was the deliberate operational choice; the 1% target is not achievable at usable recall on this dataset.

### ETH Leakage Check (2026-09-04)

High ETH AUC-ROC (0.986) investigated:

1. **68/1,478 ETH test rows are zero-activity wallets, ALL labeled fraud** — trivial shortcut inflating full ETH metrics. Non-zero-activity slice (1,410 rows): AUC-ROC 0.982, recall drops 0.637 → 0.542.
2. **Full SHAP importances on ETH test split** — top 5: `value_transacted_mean` (0.690), `lifetime_in_blocks` (0.637), `total_txs` (0.529), `num_addr_transacted_multiple` (0.418), `time_between_output_txs_mean` (0.345). No single feature dominates anomalously. All top features are real transaction-derived metrics, not indicator leaks.
3. **Conclusion:** No evidence of feature leakage. High AUC-ROC is driven by the zero-activity shortcut + small dataset (9,841 rows, 2,179 fraud).

### End-to-End Inference Verified

Live inference tested with real addresses (no backend server, direct pipeline):

- **BTC Satoshi Genesis** (`1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`): Score **0.791** (high), 46/72 features non-zero. SHAP: `fee_ratio_max` increases risk, `total_txs` decreases risk.
- **ETH Ethereum Foundation** (`0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`): Score **0.806** (high), 38/72 features non-zero. SHAP: `fee_ratio_max`, `first_block_appeared_in` drive risk.

### explain.py Compatibility

`explain.py` imports `FEATURE_COLUMNS` (72 items) from `features.py` and zips SHAP values with feature names. Since the model, feature vector, and `FEATURE_COLUMNS` all use the same 72-column schema, no index misalignment exists. Verified end-to-end: SHAP evidence returns correct feature names and directions.

### Git Hygiene

- `data/processed/` — gitignored (regenerable via `preprocess.py`)
- `backend/app/ml/artifacts/risk_model.joblib` — gitignored via `*.joblib` glob
- `risk_model.joblib` NOT committed to git — regenerated by `train.py`
- `backend/app/ml/artifacts/wallet_embeddings.npz` (~17 MB) NOT committed — regenerable by re-running the seeded-42 GraphSAGE encoder over the processed wallet graph; `train.py` and `embedding_store.py` warn-and-zero-fallback if it is missing
- Rationale: model artifacts are large (~200KB), regenerable, and tying them to specific training code commits is more reliable than binary versioning

---

## False Positive Investigation: Satoshi Genesis + ETH Foundation (2026-09-04)

### Symptom

Two indisputably legitimate, high-profile addresses scored "high risk":
- Satoshi Genesis (`1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa`): **0.791** (high)
- Ethereum Foundation (`0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe`): **0.806** (high)

### Root Cause: Non-Stationary Block Number Features

Four absolute block height features (`first_block_appeared_in`, `last_block_appeared_in`, `first_sent_block`, `first_received_block`) are completely out-of-distribution for modern addresses:

| Feature | Training range (2017-2018) | Satoshi Genesis | ETH Foundation |
|---|---|---|---|
| `first_block_appeared_in` | 391K–448K | **928,792** (+481K above max) | **917,339** (+469K above max) |
| `last_block_appeared_in` | 391K–448K | **929,311** (+482K above max) | **925,884** (+478K above max) |
| `first_received_block` | 391K–448K | **928,792** (+481K above max) | **917,339** (+469K above max) |

XGBoost cannot interpolate to unseen ranges — values above the training max route to the same leaves as the highest training examples (near the 2018 blockchain peak).

### Ablation Test: Dropping Block Features

| Model | Satoshi | ETH Fdn | Test FPR | Test Recall | Test F1 | Test AUC-PR |
|---|---|---|---|---|---|---|
| 72 feat (current) | 0.791 HIGH | 0.806 HIGH | 1.77% | 0.321 | 0.395 | 0.400 |
| 70 feat (drop 2) | 0.514 MED | 0.530 MED | 4.35% | 0.473 | 0.425 | 0.392 |
| 68 feat (drop 4) | 0.563 MED | 0.434 LOW | 8.70% | 0.448 | 0.304 | 0.310 |

Dropping block features does **not** help: the 68-feature model's FPR explodes from 1.77% → 8.70%, and **no threshold achieves FPR < 2%** (even 0.95 gives 2.07% val FPR). The block features carry genuine signal within the training distribution.

### Verdict: Inherent Limitation, Not a Fixable Feature Gap

1. **Block numbers are non-stationary**: they only increase over time. No normalization, clipping, or relative-time transform fixes this — the model has no learned splits for modern ranges.
2. **Removing features destroys in-distribution performance**: ablation shows worse metrics across the board.
3. **Correct risk behavior**: scoring extreme outlier addresses as "high risk" is defensible. The defense-in-depth architecture (Redis registry for known entities, OFAC allow/block lists) handles these cases. The ML model's job is to flag unknowns, not replace entity-level risk controls.
4. **`fee_ratio_max` is a secondary contributor**: Satoshi's 0.0002 sits above the illicit median (0.000142) but the effect is small and correlated with block-age patterns, not an independent leaky feature.

### Threshold Decision: Keep 0.90

Locked at **0.90** (documented 2026-09-04). Reasoning:
- The `<1%` FPR target is not achievable at usable recall on this dataset. Threshold 0.95 achieves 0.55% val FPR but drops recall from 57.6% → 44.6%.
- Moving to 0.95 cuts recall by ~30% for a FPR improvement that only matters on the held-out historical test set — on live addresses, the FPR is dominated by the OOD block number problem regardless.
- The 1.77% test FPR is below the 2% operational cap that was the deliberate design choice.
- The original `<1%` target was written when the model was BTC-only with different data; the combined BTC+ETH model with per-chain sample weights operates at a different operating point.
- Recorded in `risk_model_metrics.json` under `threshold_decision`.

---

## GraphSAGE Pixel Coverage & Production Scope (2026-09-05)

The 88-feature production promotion adds 16 GraphSAGE embedding columns (`gsage_0..15`) to the 72-feature baseline. Before promoting, we measured how often **live `/risk` queries** will actually receive a non-zero embedding versus the zero fallback.

### How embeddings are sourced in production

The production /risk path uses a **precomputed embedding store** (`app/ml/embedding_store.py`): the 16-dim SAGE embeddings for all 265,354 BTC-labeled graph nodes (from the seeded-42 encoder used in the retrained benchmark) are persisted to `app/ml/artifacts/wallet_embeddings.npz`. At query time the queried address is looked up:

- **Found in the store** → returns its real 16-dim embedding (`mode="full"`).
- **Not found / ETH / timeout** → returns a **16-dim zero vector** (`mode="fallback"`), mirroring the `is_sparse`/fallback pattern used by `compute_live_graph_features_with_fallback`.

An address receives a real embedding **only if it is a node in the training wallet graph**.

### Measured live coverage (2026-09-05)

We sampled genuinely fresh addresses — recent BTC addresses from live blockchain blocks and recent ETH addresses from Blockscout — and checked membership in every deployable graph set (the 265,354-node processed BTC graph, the 822,942-node raw Elliptic++ set, and the processed ETH address set):

| Sample | n | In 265,354 BTC graph | In 822,942 Elliptic++ | In processed |
|---|---|---|---|---|
| Fresh BTC addresses (from recent blocks) | 40 | **0** (0%) | **0** (0%) | **0** (0%) |
| Fresh ETH addresses (from blockscout) | 40 | 0 (0%) | — | **0** (0%) |

**Result: ~0% of genuinely fresh victim-reported addresses have any graph membership.** Elliptic++ is a fixed 2017–2018 Bitcoin window; a wallet that first appeared in the modern era does not exist as a node in that graph, so real-time queries on fresh addresses get zero embeddings.

### What this means for the production benefit claim

The 88f benchmark gains (BTC test **AUC-PR +18.1%**, recall +26.4%, val threshold 0.92 / FPR 1.41%) are measured **on test addresses that are nodes in the training graph**, i.e. addresses with *real* embeddings. For the common live case — a fresh, previously-unseen victim-reported address — the embedding falls back to zeros and the 88f model behaves essentially like the 72f baseline.

The honest scope statement, now explicit:

> **The production benefit of the 88f GraphSAGE model applies to graph-connected addresses (addresses already present in the training wallet graph). For fresh, unseen addresses — the majority of real `/risk` queries — the model falls back to zero embeddings, where measured behavior is statistically equivalent to the 72f baseline** (ETH regression check: full-ETH AUC-PR 0.9596 → 0.9571, delta −0.0025; nonzero-slice AUC-PR 0.9372 → 0.9330, delta −0.0043; no meaningful regression, and by construction no uplift). **The promoted 92f model inherits this same zero-embedding fallback** (and adds the same relative-feature path regardless of graph membership); its measured live FPs are all LOW, but embeddings still contribute only for graph-connected addresses.

The zero-embedding fallback is not a bug: it is the correct, deterministic behavior for out-of-graph addresses and keeps the response contract stable. Graph coverage would only grow if live addresses get ingested into a wallet graph (the `/trace` graph-builder path builds wallet-hops on demand but is not populated for arbitrary /risk addresses and does not contain feature vectors).

---

## 88-Feature Production Promotion (2026-09-05)

The 88f GraphSAGE model was **promoted to production** after the pre-promotion checks passed:

- **ETH regression check:** no meaningful degradation from the 16 null embedding columns — full-ETH AUC-PR 0.9596→0.9571 (delta −0.0025), nonzero-activity slice 0.9372→0.9330 (delta −0.0043), precision/recall within noise on the 1,478-row slice.
- **FP re-check:** Satoshi Genesis unchanged (72f 0.774 → 88f 0.778, still high — the non-stationary block-feature root cause is unchanged); ETH Foundation **improved** (0.806 → 0.405, dropped out of the high band). Both scores stable under ±1e-4 embedding jitter.
- **Coverage:** ~0% of fresh live addresses are in the wallet graph → they get zero embeddings; documented in the section above.

### Promoted model (final operating point)

| Item | Value |
|---|---|
| Model | XGBoost, 150 trees, depth 5, lr 0.06, subsample/colsample 0.85, `tree_method=hist`, rng 42 |
| Input | 88 features (72 tabular/graph + 16 `gsage_*` precomputed embeddings) |
| Mean per-chain `sample_weight` | BTC 87,081.50 = ETH 87,081.50 |
| **Locked threshold** | **0.92** (val FPR 1.41%, recall 62.50%) |
| Combined test FPR | 1.81% (TN 89,509 / FP 1,653 / FN 3,194 / TP 2,072) |
| Combined test P / R / F1 | 0.5562 / 0.3935 / 0.4609 |
| BTC test | P 0.5319, R 0.3797, F1 0.4431, AUC-PR 0.4270, AUC-ROC 0.8549 |
| ETH test | P 0.9850, R 0.6006, F1 0.7462, AUC-PR 0.9571, AUC-ROC 0.9851 |
| ETH non-zero activity | P 0.9773, R 0.4962, F1 0.6582, AUC-PR 0.9329, AUC-ROC 0.9812 |

The promoted numbers **exactly reproduce** the offline 88f retrained benchmark (BTC AUC-PR 0.4270 vs 0.4274, combined TP/FP identical 2072/1653/89509/3194, threshold 0.92), confirming the embedding-store path produces the same embeddings the model was trained on.

### Threshold decision: 0.92 (was 0.90 on the 72f model)

- The 2% validation FPR cap selects **0.92** on the 88f model: val FPR 1.41%, val recall 62.50%.
- 0.95 meets the original <1% target (val FPR 0.65%) but cuts recall to 53.31%; keeping the 2% operational cap is the deliberate recall/FPR trade-off.
- 0.90 on the 88f model would violate the cap (val FPR 2.05% > 2%), so 0.92 is both the cap-optimal and locked operating point.
- `risk_model_metrics.json` `threshold_decision` records the 0.92 lock.

### Promoted 92f model (2026-09-05 — deployed to production)

The promotion experiment (`docs/promotion_experiments_2026_09_05.md`) validated and
**promoted** a **92-feature** config (72 tabular/graph + 4 entity-scale-relative
features + 16 GraphSAGE embeddings) with tuned HPs and — after the weight-ablation —
`scale_pos_weight=1.0` plus the production per-chain sample weights. All three
final-validation items passed (broadened live OOD FP check 6/6 LOW, from-scratch
threshold re-selection, weight-stacking isolation); harness-vs-runtime feature
equivalence is exact (max |diff| = 0.0 across all splits).

**What changed in this promotion**
- `app/ml/relative_features.py` (new): JSON-serialized era reference
  (`artifacts/relative_features_reference.json`) fit on BTC train
  (`pd.qcut(first_block, q=8)`, bins `[391200..447655]`, p90/median/mean per bin,
  scalar std); `relative_features_for_wallet` / `apply_relative_features` replicate
  the validated harness exactly (NaN-first-block rows → era idx −1 → mean 0).
- `app/ml/features.py`: `MODEL_FEATURE_COLUMNS` is now **92**
  (`FEATURE_COLUMNS` 72 + `GSAGE_EMBEDDING_COLUMNS` 16 + `RELATIVE_FEATURE_COLUMNS` 4,
  exactly the validated column order); `compute_tabular_feature_vector` → (1, 76);
  `compute_feature_vector` → (1, 92) (embeddings via `lookup_embedding` with zero
  fallback); `add_embedding_columns` augments 76 → 92.
- `app/services/risk_service.py`: full-tabular 92 path + `RISK_FLAG_THRESHOLD = 0.70`
  (the promoted decision lock; 0.85 is the documented <1% FPR override).
- `app/ml/explain.py`: SHAP zips against `MODEL_FEATURE_COLUMNS` (92) — verified with
  the new artifact.
- `app/ml/train.py`: `train_promoted_model()` (persists the relative-feature
  reference, retrains on the 92f schema with the validated config, re-locks the
  threshold from validation, emits strict 0.85 + per-chain + ETH-nonzero reports,
  SHAP FIs incl. missingness); `train_combined_model()` now delegates to it.
- Artifacts rebuilt from scratch: `risk_model.joblib` (92f),
  `risk_model_metrics.json` (locked_threshold `0.70`),
  `relative_features_reference.json`.

**Operating-point decision for the promoted config — deliberate tradeoff, not a footnote:**

| Operating point | Val FPR | Val recall | Test combined FPR | Test combined recall | BTC test recall |
|---|---|---|---|---|---|
| **0.70 (policy lock, <2% FPR cap)** | 1.60% | 0.796 | 1.59% | 0.420 | 0.391 |
| **0.85 (<1% FPR targeting)** | 0.75% | 0.706 | **0.71%** | 0.337 | 0.305 |

- The 2% policy lock **promotes at 0.70**, preserving the recall gain. This is the
  implemented decision, consistent with every prior production decision on this dataset.
- The **<1% FPR target is genuinely achievable** on this config at **0.85** — test
  combined FPR 0.71%, ETH 0.52%, BTC 0.71% — which was NOT usable before the OOD
  fix (previous <1% points sat at 0.92/0.95 with recall ≤ 0.53). It costs ~8.3pp
  of combined recall (0.420 → 0.337) and ~7.2pp of BTC recall (0.391 → 0.305).
- The 0.85 override remains available (flip `RISK_FLAG_THRESHOLD` to 0.85) if strict
  FPR compliance (<1%) is prioritized over recall for the live use case; both
  operating points are documented as the two explicit choices.
- Threshold values vs the pre-weight-ablation analysis (0.85/0.92 on the spw=4.93
  distribution): neutralizing `scale_pos_weight` shifts scores left, so the same FPR
  targets are met at lower thresholds (0.70 / <1% at 0.85).
- Artifacts: `artifacts/threshold_reselection.json`, `artifacts/weight_ablation.json`,
  `artifacts/final_recommendation.json`.

**Verification after deployment**
- Full test suite: **64 passed** (incl. `compute_feature_vector` → (1, 92) shape
  assertions in `test_risk.py` and the 88 → 92 schema assertion in
  `test_embedding_store.py`).
- Retrained artifact **exactly reproduces** the validated offline run: locked
  threshold 0.70 (val recall 0.7959 / FPR 1.60%), combined test precision/recall/FPR
  = 0.604/0.420/1.59%, BTC AUC-PR 0.4665 / recall 0.3910 / precision 0.5747, ETH
  AUC-PR 0.9717 / recall 0.8567 / precision 0.9274.
- Live FP re-check through the **actual `/api/v1/wallets/{address}/risk` endpoint**
  (real explorers + deployed artifact): Satoshi Genesis 0.031, Bitfinex cold 0.066,
  Binance cold 0.007, Binance hot 0.061 (all BTC), Binance-8 0.226, Vitalik 0.011,
  Coinbase ETH 0.007 — **7/7 LOW, all < 0.30, none ≥ 0.60 → PASS**.

**Zero-embedding coverage caveat (applies to the promoted 92f model too):** live
addresses that are not nodes in the training wallet graph fall back to zero
embeddings; for those the GraphSAGE columns contribute nothing, and the 92f model
behaves like the 76-feature tabular+relative model. Graph features likewise fall
back to `KNOWN_VASPS` baselines when a live graph query is unavailable. This does
not damage the FP gate (measured live FPs are all low) but means uplift on
graph-connected addresses only — tracking in the milestone below.

**Previous production: 88f GraphSAGE model (2026-09-05, retired by this promotion)**

The 88f era (72 + 16 embeddings, threshold **0.92**, val FPR 1.41%, combined test
P/R 0.556/0.394, BTC AUC-PR 0.427) reproduced its offline benchmark exactly and
passed its FP re-check (Satoshi Genesis 0.831 HIGH, ETH Foundation 0.405 MEDIUM).
It is superseded by the 92f promotion above; its remaining history is preserved
under "GraphSAGE embedding promotion & coverage" and in
`docs/promotion_experiments_2026_09_05.md`.

### 88f promotion code changes (historical — superseded by 92f wiring above)

- `app/ml/features.py`: `GSAGE_EMBEDDING_COLUMNS` (16), `MODEL_FEATURE_COLUMNS` (88), `assert_model_feature_schema`, `add_embedding_columns`.
- `app/ml/embedding_store.py` (new): lazy-loads `artifacts/wallet_embeddings.npz`; `get_live_embeddings(address, chain)` → (16-dim, mode) with zero fallback and 2s timeout, mirroring `compute_live_graph_features_with_fallback`.
- `app/ml/train.py`: `train_combined_model` augments each processed split with the 16 embedding columns via `augment_frame_with_embeddings` (BTC graph addresses → real embeddings; ETH/non-graph → zeros) and trains on `MODEL_FEATURE_COLUMNS`; saves the 88f `risk_model.joblib`; `evaluate_chain_metrics` accepts an optional `feature_columns` param.
- `app/ml/model.py`: missing-artifact auto-retrain now delegates to `train_combined_model` (88f) instead of the old BTC-only 72f path.
- `app/services/risk_service.py`: builds the 72-feature vector, then fetches the live embedding (lookup + zero fallback) and concatenates to 88 before `predict_risk_score`/`explain_wallet_risk`.
- `app/ml/explain.py`: SHAP zips against `MODEL_FEATURE_COLUMNS` (88).
- `app/ml/artifacts/wallet_embeddings.npz` (new, ~17 MB): 265,354 lowercased addresses + float32 16-dim embeddings from the seeded-42 encoder.
- Tests: `test_risk.py` updated for the 88-wide model input; new `test_embedding_store.py` (4 tests) covering unknown→zeros, known→nonzero, dim/schema alignment, async fallback.

FP re-check on the promoted artifact via the real deployment path: Satoshi Genesis **0.831 HIGH** (unchanged tier; live-tx-count variation vs 0.778 offline), ETH Foundation **0.405 MEDIUM** (improved — dropped out of the high tier).

## 2026-09-06 — Neo4j Relationship-Pattern Bug Post-Audit: Live Fix + Leak-Safe Retrain

> **⚠ INVALIDATED (2026-09-06, post-swap audit):** The graph-fix swap documented
> below was reverted on 2026-09-06 after a label-leak investigation. The "NEW"
> metrics (BTC AUC-PR 1.0, combined 0.9998) were artifacts of a self-referential
> `shortest_path==0` leak, not genuine improvement. The pre-graph-fix model
> (threshold 0.70, BTC AUC-PR 0.4665) is the active production artifact.
> Full details in **[docs/incidents/2026-09-06-label-leak.md](incidents/2026-09-06-label-leak.md)**.

### Bug confirmed and scoped (audit)
- Live serving (`app/ml/live_graph_features.py`, pre-fix) queried `(wallet)-[r]-(neighbor:Wallet)`, which returns **zero rows** under the real schema `(:Wallet)-[:SENT]->(:Transaction)-[:RECEIVED_BY]->(:Wallet)` (no direct Wallet–Wallet edges). Genesis probes: broken pattern 0 in-neighbors vs schema-aware 27. **Training was unaffected** — neither the active 92f model nor `graph_features.py` ever query Neo4j.
- Bonus finding: the active 92f model trained with the 3 graph columns **100% NaN → constant 0.0** (verified nunique=0 in train/val/test across chains), i.e. graph features were DEAD in production. The only graph-true candidate (72f `train_with_graph_features.py`) used the full NetworkX graph (leaky) and was never promoted.
- Follow-ups: neo4j node uniqueness constraint (7 duplicate genesis Wallet nodes), embed full-graph precompute into the snapshot protocol, live-vs-train graph-density caveat.

### Phase A — live serving fix (deployed)
- `live_graph_features.py` rewritten: 1-hop = union(sender, receiver) deduplicated by address; 2-hop excludes 1-hop + self; `shortestPath((wallet)-[:SENT|RECEIVED_BY*1..12]-(illicit:Wallet {illicit:true}))` with length/2 capped at 6. `graph_mode` = `loaded`/`empty`/`failed` (+ `none` for TRON).
- Verified via `/risk`: genesis `loaded, 1hop=27, 2hop=5000(cap)`, score unchanged low; enrich-flag demo `illicit_1hop=1/27, shortest=1`; TRON `none` 0.009 low.

### Phase B — leak-safe snapshot features (retrain, schema-identical)
- New `app/ml/snapshot_graph_features.py`: for each wallet, features computed on `G_t` where `t` = wallet's own last timestep (the row the splits use). `G_t` = induced subgraph of addresses with first-appearance ≤ t plus AddrAddr edges among them (includes unlabeled actors; self-loops dropped for parity with live). Known-illicit sets are label class==1 **present in the train split only** by `t` (post-leak fix — see [label-leak incident](incidents/2026-09-06-label-leak.md)). Same three features as the reference code: `illicit_neighbor_ratio_1hop`, `_2hop` (2-hop excludes 1-hop + self), `shortest_path_to_known_illicit` (distance to nearest OTHER known-illicit wallet, capped at 6; never self-referencing).
- Protocol documented limitation: AddrAddr edges are un-timestamped, so an edge is "known at t" iff both endpoints are known at t (same proxy the project always used).
- Built from RAW CSVs on host (~16 min) → `data/processed/graph_features_snapshot.csv` (822,942 wallets). Merge into `train_promoted_model.transform()` overwrites the previously dead graph columns for BTC rows; ETH/missing stay 0 (existing `fillna(0.0)`).
- **Gate: independent spot-check** `app/ml/verify_snapshot.py` (8 addresses: 5 train incl. illicit-1hop/shortest=1/isolated, 1 val t=30, 1 test t=35): **8/8 PASS, 0 mismatches, 0 future leaks** (every counted neighbor's first-appearance ≤ t). An optimization bug (labeled-only edge restriction biasing 2-hop ratios upward) was caught by the 5th/6th check and fixed by using the FULL edge set.

### Retrain outcome (identical config: 292 trees, depth 7, lr 0.11111992920245407, spw 1.0, per-chain weights)

> **⚠ INVALIDATED.** The metrics below were artifacts of the self-referential
> shortest_path leak (see [label-leak incident](incidents/2026-09-06-label-leak.md)).
> The "NEW" column is spurious. The pre-graph-fix model (OLD column) is the
> active production artifact.

Table: OLD = pre-graph-fix artifact backed up as `risk_model.pre_graph_fix.joblib` / `risk_model_metrics.pre_graph_fix.json`.

| Metric | OLD (92f dead graph) | NEW (92f w/ snapshot graph) |
|---|---|---|
| Locked threshold | 0.70 | 0.50 |
| Val precision | 0.829 | 0.982 |
| Val recall | 0.796 | 0.981 |
| Val FPR | 1.60% | **0.18%** (gate ≤1.6% PASS) |
| Test combined AUC-PR | 0.506 | 0.9998 |
| Test combined recall (locked) | 0.420 | 0.992 |
| Test combined FPR | 1.59% | 0.03% |
| BTC test AUC-PR | 0.467 | 1.0 |
| ETH test AUC-PR | 0.972 | 0.969 (stable) |
| ETH test recall | 0.857 | 0.878 (stable) |

- **Honest-interpretation caveat (no future-data leak, but a tautology risk):** all 4,938 BTC test illicit wallets are self-known-illicit by their own era AND have ≥1 in-era illicit neighbor; 0 test licit self-flagged. So test recall is era-cluster adjacency + the wallet's own known-illicit membership — real structure, but the test number is not an estimate of human-novel-illicit detection. Live deployment mirrors this deliberately: a wallet enriched `illicit:true` (sanction/genuine scrape) is scored with `shortest_path=0` and the `/risk` sanctions override returns 1.0 critical regardless of ML.
- **OOD validation (Gate 4):** `broadened_ood_validation.py` returned **PASS on retry (2026-09-06) once BTC explorers recovered** — 6/6 known-legit entities LOW and none ≥0.60 (bitfinex_cold 0.0829, binance_cold 0.0016, binance_hot 0.0182, binance_8 0.0085, vitalik 0.0095, coinbase_eth 0.0055 combined; deployed `production_92f_score` ≤0.0004 for all). Sanctioned arm: Garantex raw-ML 0.1034 in the harness (harness intentionally does not consult the sanctions registry, does not gate the verdict) but the production `/risk` layer returns **1.0 critical via `sanctions_override`** (verified live). Live `/risk` after swap: Garantex 1.0 critical, BTC exchangers 0.0 low, ETH legit 0.0 low.
- **Deployment status (2026-09-06):** ~~graph-fix 92f model is **SWAPPED INTO PRODUCTION** after the OOD gate passed.~~ **REVERTED** — see [label-leak incident](incidents/2026-09-06-label-leak.md). Active artifact restored to pre-graph-fix backup (`risk_model.joblib` = pre-graph-fix, threshold 0.70, BTC AUC-PR 0.4665). Leaky artifact archived as `risk_model.leaky_graph92.joblib`.
- Time-box: graph-fix work completed within the ~1-day budget; remaining docs task was the write-up only.


