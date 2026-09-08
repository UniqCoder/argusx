# Promotion Experiment Report (2026-09-05)

Targeted, low-risk improvements to the 88-feature production model (XGBoost +
precomputed GraphSAGE embeddings). All arms run offline on the **same**
`data/processed/*.csv` splits and **same** precomputed embedding store as
production, so results are apples-to-apples. Baseline reproduction on the
harness is exact (BTC AUC-PR 0.4274 / recall 0.3797 @ threshold 0.92).

## Side-by-side vs production baseline (BTC test holdout)

| Arm | BTC AUC-PR | BTC Recall | BTC Precision | BTC FPR | Threshold | Val FPR | vs AUC-PR | vs Recall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **Production baseline** | **0.4270** | **0.3797** | **0.5319** | 0.0183 | 0.92 | 1.41% | — | — |
| Task 1: relative features (92f) | 0.4416 | 0.3489 | 0.5655 | 0.0147 | 0.92 | 1.39% | **+3.3%** | **−8.1%** |
| Task 3: Optuna-tuned HPs (88f) | 0.4456 | 0.4024 | 0.5005 | 0.0220 | 0.75 | 1.95% | **+4.3%** | **+6.0%** |
| Task 4: vanilla SMOTE (BTC) | 0.4365 | 0.3601 | 0.5320 | 0.0174 | 0.92 | 1.38% | +2.1% | **−5.2%** |
| Task 4: borderline-SMOTE (BTC) | 0.3348 | 0.1974 | 0.4992 | 0.0109 | 0.92 | 1.67% | **−21.6%** | **−48.0%** |
| **Task 1 + 3 combined (92f + tuned HPs)** | **0.4633** | **0.3967** | **0.5480** | 0.0179 | **0.85** | 1.67% | **+8.4%** | **+4.5%** |

## Verdicts

### Task 1 (relative features) — mixed, keep as ingredient
- Adds `total_txs_pctile_era`, `value_transacted_total_pctile_era`, `total_txs_z_era`,
  `value_transacted_total_z_era` (percentile / z-score vs same-era BTC peers,
  era bucketed by `first_block_appeared_in`, reference fit on BTC-train only).
- Improves AUC-PR and precision, lowers FPR — but **recall drops below the 38%
  gate** (0.349). Not promotable alone. Confirmed it stops conflating scale with
  risk.
- Live OOD diagnostic (curated-profile proxy through real /risk feature path):
  Satoshi Genesis 0.419 → **0.275 (medium → low, −0.14)**; ETH Foundation stays
  low (+0.05 noise). Directionally confirms the intended fix on the exact
  Satoshi-style case.

### Task 3 (Optuna tuning) — good but precision/tradeoff caveat
- Optuna (40 trials, TPE, maximize combined-val AUC-PR) over learning_rate,
  max_depth, n_estimators, subsample, colsample_bytree, scale_pos_weight.
  Best: lr=0.111, depth=7, n_est=292, subsample=0.917, colsample=0.757,
  scale_pos_weight=4.93 (val AUC-PR 0.8777).
- Improves AUC-PR +4.3% and recall +6.0%, but precision drops (0.532→0.501) and
  combined test FPR rises to 2.2% (val FPR 1.95% still within cap). Threshold
  moved 0.92→0.75.

### Task 4 (SMOTE / borderline-SMOTE) — not viable
- Vanilla SMOTE: AUC-PR +2.1% but recall −5.2% (below gate). Borderline-SMOTE
  clearly worse (AUC-PR −21.6%, recall −48%). Synthetic feature-space
  interpolations in the BTC heavy-tailed distribution do not transfer to the
  temporal test set.

### Combined Task 1 + 3 — **RECOMMENDED FOR PROMOTION**
- 92 features + tuned HPs, threshold 0.85, val FPR 1.67% (< 2% cap).
- **Simultaneously improves** BTC AUC-PR (+8.4%), recall (+4.5%), precision
  (+3.0%), and lowers FPR. Combined AUC-PR 0.454→0.502.
- Recover of the Task-1 recall loss is the tuned HPs; the net gain is the
  largest of any single arm.

## Pre-promotion checks (winning config — all PASS)
1. **ETH regression check** ✅ — AUC-PR 0.9710 (prod 0.9571), recall 0.8598 (prod 0.6006), AUC-ROC 0.9902 (prod 0.9851).
2. **Embedding-jitter stability** ✅ — FP profiles spread < 0.0024; 200 BTC test rows max-abs-delta **0.0** on embedding dims.
3. **FP re-check** ✅ — Satoshi Genesis **0.0041 LOW**, Ethereum Foundation **0.0043 LOW** (both clear the high/medium bands vs prod 0.419/0.229 on the same curated profile).
4. **Full backend test suite** ✅ — **64 passed** (no regressions).

## Promotion wiring (completed 2026-09-05 — 92f is now the deployed artifact)
1. `compute_feature_vector` produces the 4 relative features on the live path from
   an OOD-safe JSON reference artifact (`artifacts/relative_features_reference.json`),
   fit once on BTC train (8 era bins) — not recomputed per-request.
2. `MODEL_FEATURE_COLUMNS` = 72 tabular + 4 relative + 16 embeddings = **92**
   (`compute_tabular_feature_vector` → 76; `add_embedding_columns` 76+16 → 92);
   `risk_service.py` uses the full 92 path with `RISK_FLAG_THRESHOLD = 0.70`;
   `explain.py` SHAP zips against the 92 names; `assert_model_feature_schema` covers 92.
3. Retrained `risk_model.joblib` with **scale_pos_weight=1.0** (final arm B),
   persisted the relative-feature reference, locked threshold **0.70** (val recall
   0.7959 / FPR 1.60%), and refreshed `risk_model_metrics.json` — test P/R/FPR
   reproduce the offline final benchmark (0.604/0.420/1.59%, BTC AUC-PR 0.4665).
4. `docs/ml.md` updated (92f PROMOTED, 88f retired to history) and the artifact JSON
   refreshed; full test suite **64 passed**; live `/risk` endpoint FP re-check
   **7/7 LOW** (none ≥ 0.60).

## Final validation before promotion (all three items — all CLEAR)

### Item 1 — Broadened OOD FP validation with 6 REAL addresses ✅ **PASS (6/6 LOW)**
Live explorer lookups (no synthetic profiles) through the exact `risk_service`
feature path (`compute_feature_vector` + graph-feature fallback + zero-embedding
fallback + relative features), scored with production 88f **and** the combined 92f
model. SHAP top-5 drivers recorded per address.

| Entity | Chain | tx_events | 88f prod score (tier) | **92f score (tier)** |
|---|---:|---:|---:|---:|
| Bitfinex cold | BTC | 57 | 0.6228 (high) | **0.1765 (low)** |
| Binance cold | BTC | 6543 | 0.2051 (low) | **0.0098 (low)** |
| Binance hot (1.19M txs) | BTC | 112 | 0.6484 (high) | **0.1874 (low)** |
| Binance-8 | ETH | 25 | 0.7287 (high) | **0.0442 (low)** |
| Vitalik Buterin | ETH | 25 | 0.6388 (high) | **0.0197 (low)** |
| Coinbase ETH | ETH | 25 | 0.4483 (medium) | **0.0452 (low)** |

- `tx_events` = RawTx output legs from ≤25 on-chain txs (exchange consolidation txs
  have 2–260+ outputs), identical to how the production `/risk` path consumes data.
- **Vanity check met**: 3 of 6 addresses are flagged **high (0.62–0.73)** by the
  current production artifact, yet all 6 score low under the combined 92f config —
  the fix generalizes well beyond the Satoshi/ETH-Fdn anchors it was first seen on.
- SHAP confirms the mechanism: `first_block_appeared_in` / `first_received_block`
  / `total_txs_z_era` / `num_addr_transacted_multiple` all push *decreases_risk`.
- Artifact: `artifacts/broadened_ood_validation.json`.

### Item 2 — Threshold re-selected from scratch + test-split confirmation ✅
Fresh scan on the combined model's **own** validation distribution (nothing reused
from the old 0.92 lock). On the **arm A** distribution: policy lock **0.85**
(val FPR 1.67%), and the <1% override at **0.92** (val FPR 0.99%). **Test split:**

| Threshold | Split | Precision | Recall | FPR |
|---|---|---|---|---|
| 0.85 | BTC / ETH / combined | 0.548 / 0.946 / 0.579 | 0.397 / 0.860 / 0.426 | 1.80% / 1.39% / **1.79%** |
| 0.92 | BTC / ETH / combined | 0.683 / 0.968 / 0.711 | 0.358 / 0.832 / 0.387 | 0.91% / 0.78% / **0.91%** |

→ The <1% FPR target is **achievable on test** at 0.92 (0.91%), at a real recall
cost (combined 0.426 → 0.387). Artifact: `artifacts/threshold_reselection.json`.

### Item 3 — Weight-ablation: does `scale_pos_weight` stack? ✅ **spw is redundant**
All four arms = identical 92f features + identical tuned HPs; each re-locks its own
threshold from its own validation scan.

| Arm | sample_weight | scale_pos_weight | Locked thr | BTC AUC-PR | BTC Recall | BTC Prec | BTC FPR |
|---|---|---|---|---|---|---|---|
| A | chain | 4.93 | 0.85 | 0.4633 | 0.3967 | 0.5480 | 1.80% |
| **B** | chain | **1.0** | 0.70 | **0.4666** | 0.3910 | **0.5747** | **1.59%** |
| C | uniform | 4.93 | 0.50 | 0.4725 | 0.3793 | 0.6048 | 1.36% |
| D | uniform | 1.0 | 0.50 | 0.4529 | 0.3143 | 0.5828 | 1.23% |

- **B ≈ A** (ΔAUC-PR +0.0033 < 0.005, Δrecall −0.6pp < 1pp) → the tuned
  `scale_pos_weight=4.93` is **redundant double-correction** on top of the
  per-chain sample weights. Neutralizing it is harmless-to-better (higher AUC-PR,
  +2.7pp precision, lower FPR).
- Per-chain `sample_weight` is the **real** lever: clearing it (D floor) collapses
  BTC recall to 0.314. Neither weight mechanism alone reproduces A, but the
  marginal SPW increment adds ~nothing once chain weights are present.
- **→ Promote with `scale_pos_weight=1.0` (arm B).** Artifact: `artifacts/weight_ablation.json`.

### Final consolidated operating point (arm B) ✅ `artifacts/final_recommendation.json`
- Config: 92f + tuned HPs (lr 0.111, depth 7, n_est 292, subsample 0.917,
  colsample 0.757) + **spw=1.0** + per-chain sample weight.
- **Promoted operating point: threshold 0.70** (val FPR 1.60%, val recall 0.796).
- Test @ 0.70: BTC **AUC-PR 0.4666 / recall 0.391 / precision 0.575 / FPR 1.59%**;
  ETH AUC-PR 0.972 / recall 0.857; combined AUC-PR 0.506 / recall 0.420 / FPR 1.59%.
- **<1% FPR override: threshold 0.85** (val FPR 0.75%; **test** combined FPR 0.71%,
  BTC 0.71%, ETH 0.52%). Tradeoff: combined recall 0.420 → 0.337, BTC recall
  0.391 → 0.305. Because spw is neutral (arm B), the score distribution shifts left,
  so the <1% target is met at **0.85** — materially better than arm A's 0.92 point.

**Promotion decision: GO** — promote final arm B at threshold **0.70** (policy lock);
document **0.85** as the <1%-FPR override for the target owner to review (docs/ml.md).