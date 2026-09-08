# GraphSAGE Closure & Engineered Graph Features Implementation — 2026-09-01

## Status Summary

**Part 1 (Documentation):** ✅ COMPLETE  
**Part 2 (Implementation):** 🔄 IN PROGRESS (waiting for graph feature precomputation)

---

## Part 1: GraphSAGE Investigation Closure ✅

### 1.1 Documentation Updated ✅
- **docs/ml.md**: Replaced "verified uplift" language with honest conclusion
  - GraphSAGE embeddings evaluated under identical-hyperparameter comparison vs baseline
  - **Fair result**: 0.3974 AUC-PR baseline → 0.3827 with embeddings (-3.7%)
  - Earlier "uplift" was measurement artifact due to hyperparameter mismatch in benchmark
  - GraphSAGE marked as non-production research, code retained for reference
  - Rationale documented: live inference infeasible on sparse neighborhoods, interpretability trade-off

- **docs/ml.md**: New section added for engineered graph features approach
  - Simpler, more interpretable alternative to GNNs
  - Three features: `illicit_neighbor_ratio_1hop`, `illicit_neighbor_ratio_2hop`, `shortest_path_to_known_illicit`
  - Uses same training-period graph (`AddrAddr_edgelist.csv`) with no leakage
  - Fair retraining protocol: EXACT baseline hyperparameters, only feature set changes

### 1.2 Progress Log Updated ✅
- **progress.md**: Dated 2026-09-01 entry documenting
  - What was tried: GraphSAGE offline benchmark with 2-layer encoder
  - What was found: Hyperparameter mismatch made comparison invalid
  - Why it was dropped: Fair retraining too expensive, simpler engineered features more practical
  - Full audit reference: [GRAPHSAGE_AUDIT_FINDINGS.md](../GRAPHSAGE_AUDIT_FINDINGS.md)

---

## Part 2: Engineered Graph Features Implementation 🔄

### 2.1 Graph Feature Computation Script ✅ + 🔄

**Created:** `backend/app/ml/graph_features.py`
- Loads training-period graph (time steps 1-29 only, no test leakage)
- Uses NetworkX for efficient graph algorithms
- Computes for each wallet:
  - `illicit_neighbor_ratio_1hop`: % of direct neighbors labeled illicit
  - `illicit_neighbor_ratio_2hop`: % of 2-hop neighbors labeled illicit (excluding 1-hop)
  - `shortest_path_to_known_illicit`: minimum distance to any illicit node (capped at 6)
- Optimization: Precomputes all-pairs shortest paths from illicit nodes to avoid per-node recomputation
- **Status**: Currently running (504/7624 illicit nodes precomputed, ~35-50 min remaining)

**Invocation:**
```bash
python -m backend.app.ml.graph_features backend/data/raw/ellipticpp
```

### 2.2 Feature Schema Updated ✅

**File:** `backend/app/ml/features.py`
- Added `GRAPH_FEATURE_COLUMNS` list: 3 new engineered features
- Updated `FEATURE_COLUMNS`: 62 → 65 total features
  - 55 tabular (Elliptic++ canonical schema)
  - 7 missing indicators
  - 3 graph topology features
- Updated docstring: clearly documents 65-feature schema
- `assert_feature_schema()` guard remains active (enforces schema in all training/inference)

### 2.3 Training with Graph Features Script ✅

**Created:** `backend/app/ml/train_with_graph_features.py`

**Key Features:**
- Loads graph features computed by `graph_features.py`
- Merges with Elliptic++ tabular features on address
- **Fair retraining protocol** — uses EXACT production baseline hyperparameters:
  ```python
  n_estimators=150
  scale_pos_weight=computed (same as baseline)
  max_depth=5
  learning_rate=0.06
  subsample=0.85
  colsample_bytree=0.85
  ```
- **Only change:** Input features (62 → 65)
- Ensures metric differences are attributable to engineered graph features, not model config
- Threshold locked via standard validation-split procedure (2% FPR cap)
- Outputs:
  - Trained model: `artifacts/risk_model_with_graph_features.joblib`
  - Metrics report: `artifacts/risk_model_metrics_with_graph_features.json`
  - SHAP importance for each graph feature

**Invocation** (after graph features complete):
```bash
python -m backend.app.ml.train_with_graph_features
```

### 2.4 Live Neo4j Graph Feature Computation ✅

**Created:** `backend/app/ml/live_graph_features.py`

**Key Functions:**
- `compute_live_graph_features(client, address, chain)` — async Neo4j queries
  - 1-hop query: immediate neighbors and illicit status
  - 2-hop query: 2-hop neighbors (excluding 1-hop), illicit status
  - Shortest path query: minimum distance to any illicit node
- `compute_live_graph_features_with_fallback()` — timeout resilience
  - If Neo4j queries time out (>2s), returns zeroed graph features
  - Mode indicator: `"full"` (Neo4j query succeeded) or `"fallback"` (timeout/error)
  - Ensures inference doesn't hang; traces mode in logs

**Integration Point:**
- Will be called by `/api/v1/wallets/{address}/risk` after feature extraction
- Uses same 3 engineered features from training, computed live from current Neo4j state

### 2.5 SHAP Factor Report Script ✅

**Created:** `backend/app/ml/shap_report.py`

**Purpose:** Generate SHAP contribution analysis for demo addresses

**Demo Addresses (hardcoded):**
- `garantex_deposit`: 3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1 (BTC, known illicit, OFAC SDN 2025-08-14)
- `lazarus_proxy`: TLa2f6VPqDMsaxQVj7FSrsDjjQuT5Zox1g (TRON, known scam)
- `satoshi_genesis`: 1A1z7agoat4wr8GkidKjsKtdGuwAks2t24 (BTC, historical unique)

**Output:** `artifacts/shap_demo_report.json`
- Predicted risk score for each demo address
- Top 10 contributing features (sorted by SHAP magnitude)
- Separate section highlighting graph feature contributions
- Value + SHAP contribution for each feature

**Invocation**:
```bash
python -m backend.app.ml.shap_report --model-path artifacts/risk_model_with_graph_features.joblib
```

---

## Part 2: Remaining Steps 🔄

### Step 1: Wait for Graph Computation (35-50 min remaining)
- Terminal ID: `35097e34-f95a-4d5e-9c65-38103eb89080`
- Current progress: 504/7624 illicit nodes (6.6%)
- Once complete, will output:
  ```
  First 10 rows:
  [DataFrame with columns: address, illicit_neighbor_ratio_1hop, illicit_neighbor_ratio_2hop, shortest_path_to_known_illicit]
  
  Shape: (152613, 4)
  ```

### Step 2: Run Training with Graph Features (10-15 min)
```bash
cd c:\vs code\SIH
python -m backend.app.ml.train_with_graph_features
```

**Expected Output:**
- Model trained on 215,725 training samples (time steps 1-29)
- Threshold locked on 11,647 validation samples (time steps 30-34)
- Held-out test results on 36,453 samples (time steps 35-49):
  - Test AUC-PR, AUC-ROC
  - Test Precision, Recall, FPR at locked threshold
  - Comparison vs production baseline (0.3774 AUC-PR)
  - SHAP importance for each of 3 graph features

### Step 3: Generate SHAP Report (5 min)
```bash
python -m backend.app.ml.shap_report \
  --model-path artifacts/risk_model_with_graph_features.joblib \
  --output-path artifacts/shap_demo_report.json
```

---

## Expected Outcomes

### If Graph Features Improve Metrics (Best Case)
- Report improvement in AUC-PR over 0.3774 baseline
- Show which demo addresses benefit most from graph signal
- SHAP report proves features are interpretable (not black-box embeddings)
- Live Neo4j queries are feasible (sparse neighborhood fallback available)
- New model becomes candidate for production replacement

### If Graph Features Do NOT Improve Metrics (Still Useful)
- Provides evidence that temporal window, not missing graph signal, is the bottleneck
- Validates that simple engineered features exhausted the graph-based approaches
- Justifies continued use of registry + deterministic blocking (Phase 2) as primary risk layer
- Honest finding documented in progress.md for future engineers

---

## Files Created/Modified

### Created (New)
- `backend/app/ml/graph_features.py` — Graph feature computation (NetworkX-based)
- `backend/app/ml/train_with_graph_features.py` — Fair retraining with graph features
- `backend/app/ml/live_graph_features.py` — Live Neo4j graph feature queries
- `backend/app/ml/shap_report.py` — SHAP contribution analysis for demo addresses

### Modified
- `backend/app/ml/features.py` — Added `GRAPH_FEATURE_COLUMNS` (3 features, 65 total)
- `docs/ml.md` — Honest GraphSAGE conclusion + engineered graph features section
- `docs/progress.md` — Dated 2026-09-01 entry documenting closure

### Reference Only (Not Modified)
- `backend/app/ml/graphsage_risk.py` — Retained as non-production research artifact
- `GRAPHSAGE_AUDIT_FINDINGS.md` — Full methodological audit for reference

---

## Next: Monitor Graph Computation

Terminal continues running. You can check progress anytime with:
```bash
# Check last output of the computation
get_terminal_output id=35097e34-f95a-4d5e-9c65-38103eb89080
```

Once complete (expect ~45 min total), we run the training step and generate final metrics report.
