# GraphSAGE vs Tabular XGBoost Comparison Results

**Date:** 2026-09-05 (retrained on `data/processed/` splits)
**Test Location:** c:\vs code\SIH\backend
**Python:** 3.13.12
**Dataset:** Processed Elliptic++ BTC + Ethereum (174,163 train / 23,841 val / 96,428 test; 265,354 labeled BTC graph nodes)

---

## Retrained Benchmark — Apples-to-Apples With Production [2026-09-05]

### Why This Supersedes Previous Numbers

The old benchmark (2026-09-01) trained GraphSAGE off the **raw** dedup/rename path and fitted XGBoost with `scale_pos_weight` on a **BTC-only** slice. Production now trains on `data/processed/` splits with **per-chain `sample_weight`** on the **combined BTC+ETH** set at **threshold 0.90**. The retrained benchmark mirrors `train_combined_model` exactly.

### Fairness verification

The retrained **baseline arm (72 features, `sample_weight`, combined-val threshold 0.90) reproduces production metrics almost exactly:**

| Metric | Retrained baseline | Production (`risk_model_metrics.json`) |
|---|---|---|
| BTC test AUC-PR | 0.3620 | 0.3607 |
| BTC test Precision | 0.4795 | 0.4795 |
| BTC test Recall | 0.3003 | 0.3003 |
| CAGR test TP/FP/TN/FN | 1692/1613/89549/3574 | 1692/1613/89549/3574 |

Pre-processing differences are the only delta, so the GraphSAGE arm is a fair, controlled experiment.

### Comparison (BTC test, harder benchmark)

| Metric | 72f Tabular | 88f Tabular+GraphSAGE | Δ |
|---|:---:|:---:|:---:|
| **Test AUC-PR** | 0.3620 | 0.4274 | **+18.1%** |
| Test AUC-ROC | 0.8432 | 0.8549 | +1.4% |
| Test Precision | 0.4795 | 0.5319 | +10.9% |
| Test Recall | 0.3003 | 0.3797 | +26.4% |
| Test FPR | 1.79% | 1.83% | ~flat |
| Val Threshold | 0.90 | 0.92 | + |
| Val Recall (locked thresh) | 0.5762 | 0.6250 | +8.5pp |
| Val FPR (locked thresh) | 1.91% | 1.41% | −0.5pp |

### Combined test (all chains)

| Metric | 72f Tabular | 88f Tabular+GraphSAGE | Δ |
|---|:---:|:---:|:---:|
| Test Precision | 0.5120 | 0.5562 | +8.6% |
| Test Recall | 0.3213 | 0.3935 | +22.5% |
| Test FPR | 1.77% | 1.81% | ~flat |
| Test TP/FP/TN/FN | 1692/1613/89549/3574 | 2072/1653/89509/3194 | TP +380 |

GraphSAGE lifts precision, recall, and AUC-PR at essentially unchanged FPR, and it locks a stricter threshold (0.92) because the validation slice is cleaner (precision 0.812, recall 0.625).

### How embeddings are applied

- Node set = 265,354 labeled BTC wallets (train+val+test from processed splits), identical to production.
- 2-layer `SAGEConv` (hidden 32, embedding 16) trained on train nodes with **train-only edges** (481,298 undirected) to avoid leakage; embeddings extracted with the full labeled graph.
- ETH test rows have no wallet-graph node and receive **zero-vector embeddings** (16 zeros). This is deliberate and documented — the 88f arm still improves on BTC; ETH contribution is unchanged.
- XGBoost arms use production hyperparameters (150 trees, depth 5, lr 0.06, subsample/colsample 0.85, `tree_method=hist`, random_state 42) with per-chain `sample_weight`.

### Production scope caveat (2026-09-05)

The gains above (AUC-PR +18.1%, recall +26.4%) are realized by **test addresses that are nodes in the training graph** (real embeddings). Coverage measurement sampled **40 fresh live BTC + 40 fresh ETH addresses** and found **0% membership** in the 265,354-node graph / 822,942 Elliptic++ / processed ETH set. In production, fresh victim-reported addresses fall back to **zero embeddings** (see `ml.md` "GraphSAGE Pixel Coverage & Production Scope"), where the 88f model is statistically equivalent to the 72f baseline (ETH regression check: AUC-PR delta ≤ 0.004). Treat the benchmark uplift as applying to graph-connected addresses, not the general fresh-address population.

### Graph data validation (2026-09-05)

- `AddrAddr_edgelist.csv` reads cleanly with `header=0` (previous `header=None` created a bogus `input_address→output_address` edge, silently filtered).
- Edgelist and deduped wallet set share exactly 822,942 addresses (0 missing each way) — no reconciliation needed. 45,981 self-loops; 1,118,222 edges between labeled (class 1/2) endpoints; 17,211 labeled wallets isolated in the labeled subgraph (6.49%).
- **Case normalization:** the preprocessing pipeline lowercases BTC base58 addresses; the raw edgelist is preserve-case. Verified processed BTC addresses == lowercased labeled set with **zero collisions**; loader now lowercases edgelist endpoints to match.

---

## Previous Benchmark (Superseded — raw path, `scale_pos_weight`) [2026-09-01]

The pre-retrain comparison trained off raw CSVs with `scale_pos_weight` on BTC-only slices and concluded GraphSAGE **degraded** AUC-PR (0.3974 → 0.3827 fair). Those numbers are **not comparable** to the production model trained on `data/processed/` splits and are superseded by the 2026-09-05 retrained benchmark above. Root cause of the old conclusion: mismatch between baseline/GraphSAGE training inputs (raw rename path vs processed splits) and weighting strategy (`scale_pos_weight` vs per-chain `sample_weight`), which the retrained run removes.

---