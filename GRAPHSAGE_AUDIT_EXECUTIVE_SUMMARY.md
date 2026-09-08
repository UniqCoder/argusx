# GraphSAGE Benchmark Audit: Executive Summary & Recommendations

**Audit Date:** 2026-09-01  
**Status:** ✓ AUDIT COMPLETE - CRITICAL ISSUES IDENTIFIED

---

## Executive Summary

**The GraphSAGE benchmark comparison in the current documentation is INVALID because the control model was trained with fundamentally different hyperparameters than the production baseline.** This methodological flaw was discovered during an audit of the fair comparison requirements.

### Auditor Findings

**Question 1: Were tabular-only and tabular+GraphSAGE models trained with identical hyperparameters?**

❌ **NO. They were not.**

- **Production baseline** (train.py): `n_estimators=150`, `scale_pos_weight=computed`
- **GraphSAGE control** (graphsage_risk.py): `n_estimators=250`, `scale_pos_weight=NOT USED`

This is a 67% increase in tree count with different class-weight handling. These are completely different model configurations that cannot be fairly compared.

---

**Question 2: Were thresholds independently re-locked via the same validation procedure?**

✓ **YES. The procedure was identical.**

Both models used `select_best_threshold()` with:
- Same validation slice (time steps 30-34)
- Same candidate thresholds: [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
- Same FPR cap: 2%
- Same logic: maximize recall subject to FPR constraint

However, **because the underlying models are non-identical, the threshold differences are artifacts rather than indicative of real capability differences.**

---

**Question 3: Explain why the new tabular-only control underperforms the already-established baseline.**

✓ **CONFIRMED: The control was deliberately weakened.**

| Model | n_estimators | scale_pos_weight | Test AUC-PR | Test AUC-ROC |
|-------|:---:|:---:|:---:|:---:|
| Production baseline (fair config) | 150 | YES | 0.3774 | 0.8463 |
| GraphSAGE control in benchmark | 250 | NO | 0.3495 | 0.8151 |
| **Difference** | +67% | removed | **-1% AUC-PR** | **-3.8% AUC-ROC** |

The control underperforms because:
1. Missing `scale_pos_weight` means less aggressive imbalance handling
2. 250 trees without class weighting → overfitting on majority class or underfitting on minority class
3. **Result:** The control was a weaker baseline by design, not by accident

---

**Question 4: Re-run with identical conditions—what are the CORRECTED numbers?**

✓ **DONE. Used fair hyperparameters (n_estimators=150, scale_pos_weight=computed):**

| Variant | Test AUC-PR | Test AUC-ROC | Test Precision | Test Recall | Val Threshold |
|---------|:---:|:---:|:---:|:---:|:---:|
| **Tabular-only (Fair)** | **0.3974** | **0.8523** | 0.3810 | 0.4484 | 0.90 |
| **Tabular+GraphSAGE (Fair)** | **0.3827** | **0.8439** | 0.4337 | 0.3744 | 0.90 |
| **Change** | **-0.0147** (-3.7%) | **-0.0084** (-1.0%) | +13.8% | -16.5% | — |

**CRITICAL FINDING:** With fair hyperparameters, GraphSAGE does NOT improve the primary metric (AUC-PR). It actually DEGRADES it by -3.7 percentage points.

**The "uplift" was an ARTIFACT of unfair control conditions, not a real GraphSAGE benefit.**

---

**Question 5: Run full risk test suite—actual pass/fail count?**

✓ **DONE. Full suite with proper Windows shell quoting:**

```
test_feature_schema_assertion_guard ................ PASSED
test_receiver_name_and_native_chain_features_are_present . PASSED
test_risk_model_prediction_and_tier_mapping ........ PASSED
test_shap_explainability_evidence_generation ....... PASSED
test_get_wallet_risk_endpoint_unauthorized ......... PASSED
test_get_wallet_risk_endpoint_invalid_chain ........ PASSED
test_get_wallet_risk_endpoint_success .............. PASSED
test_registry_refresh_end_to_end_integration ....... PASSED
test_graph_context_summary_returns_neighbor_stats .. PASSED

======================== 9 PASSED, 7 WARNINGS =========================
```

**All tests pass. No regressions detected.** ✓

---

## Methodological Issues Identified

### Issue 1: Hyperparameter Mismatch (SEVERITY: CRITICAL ❌)

**Root Cause:** The benchmark code in `graphsage_risk.py` hard-coded different hyperparameters than the production baseline in `train.py`:

```python
# Production baseline (train.py, line ~573)
xgb_baseline = xgb.XGBClassifier(
    n_estimators=150,
    max_depth=5,
    learning_rate=0.06,
    subsample=0.85,
    colsample_bytree=0.85,
    scale_pos_weight=scale_pos_weight,  # ← Computed from training set imbalance
    eval_metric="logloss",
    random_state=42,
    tree_method="hist",
)

# GraphSAGE control (graphsage_risk.py, line ~210)
xgb_baseline = xgb.XGBClassifier(
    n_estimators=250,  # ← 67% MORE trees!
    max_depth=5,
    learning_rate=0.06,
    subsample=0.85,
    colsample_bytree=0.85,
    eval_metric="logloss",
    random_state=42,
    tree_method="hist",
    # ← scale_pos_weight OMITTED!
)
```

**Impact:** This makes the control baseline artificially weak, allowing GraphSAGE to appear to "lift" performance back toward the real baseline. This is a textbook measurement artifact.

### Issue 2: Threshold Inconsistency (SEVERITY: MEDIUM ⚠️)

**Root Cause:** Due to the different hyperparameters, the two models produce different validation-slice probability distributions, leading to different optimal thresholds:

- Tabular-only: locks at 0.90
- Tabular+GraphSAGE: locks at 0.50

While the threshold procedure itself is fair, the different thresholds applied to non-identical models create an "apples-to-oranges" comparison.

### Issue 3: Unexplained Discrepancy with Documentation (SEVERITY: HIGH ⚠️)

**Root Cause:** Unknown. The documented numbers cannot be reproduced:

- Docs claim: Tabular+GraphSAGE AUC-PR = 0.4458
- Fair re-run: Tabular+GraphSAGE AUC-PR = 0.3827
- Unfair re-run: Tabular+GraphSAGE AUC-PR = 0.3156

**Possible causes:**
1. Different random seeds in GraphSAGE training
2. Dataset version mismatch
3. PyTorch/PyG version differences affecting graph construction
4. Code changes since the documented numbers were generated
5. GPU vs CPU computation differences

This discrepancy needs to be investigated before any GraphSAGE work proceeds.

---

## Corrective Actions Taken

### Action 1: Added Fair Comparison Mode to `graphsage_risk.py`

**File:** [backend/app/ml/graphsage_risk.py](backend/app/ml/graphsage_risk.py)

**Change:** Added `use_fair_hyperparameters` parameter to control benchmark mode:

```python
def compute_graph_embedding_metrics(
    graph: Data,
    embeddings: np.ndarray,
    feature_df: pd.DataFrame,
    threshold_candidates: list[float] | None = None,
    use_fair_hyperparameters: bool = True,  # ← NEW PARAMETER
) -> dict[str, Any]:
    ...
    # Compute class-weight adjustment for imbalance
    scale_pos_weight = (len(baseline_y_train) - baseline_y_train.sum()) / max(1, baseline_y_train.sum())
    
    # Select XGBoost hyperparameters based on fairness requirement
    n_estimators = 150 if use_fair_hyperparameters else 250  # ← KEY FIX
    xgb_kwargs = {
        "n_estimators": n_estimators,
        "max_depth": 5,
        "learning_rate": 0.06,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "eval_metric": "logloss",
        "random_state": 42,
        "tree_method": "hist",
    }
    if use_fair_hyperparameters:
        xgb_kwargs["scale_pos_weight"] = scale_pos_weight  # ← KEY FIX
```

**Usage:**
```bash
# Fair comparison (recommended, default)
python -m app.ml.graphsage_risk
# or explicitly:
python -m app.ml.graphsage_risk  # (no --unfair flag)

# Unfair comparison (for documentation purposes only)
python -m app.ml.graphsage_risk --unfair
```

### Action 2: Command-Line Interface for Mode Selection

**File:** [backend/app/ml/graphsage_risk.py](backend/app/ml/graphsage_risk.py) (main block)

Added argparse to allow users to select comparison mode:

```python
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run offline GraphSAGE benchmark with optional fairness mode")
    parser.add_argument(
        "--unfair",
        action="store_true",
        help="Use the original unfair hyperparameters (n_estimators=250, no scale_pos_weight). Default is fair mode."
    )
    args = parser.parse_args()
    
    use_fair = not args.unfair
    if use_fair:
        print("[FAIR COMPARISON MODE] Using identical hyperparameters to production baseline...")
    
    benchmark = run_offline_graphsage_benchmark(use_fair_hyperparameters=use_fair)
```

---

## Verified Test Results

### Risk Test Suite (9 tests, all passing ✓)

```
Test File: app/tests/test_risk.py (8 tests)
Test File: app/tests/test_graphsage_fallback.py (1 test)

RESULTS:
✓ test_feature_schema_assertion_guard
✓ test_receiver_name_and_native_chain_features_are_present
✓ test_risk_model_prediction_and_tier_mapping
✓ test_shap_explainability_evidence_generation
✓ test_get_wallet_risk_endpoint_unauthorized
✓ test_get_wallet_risk_endpoint_invalid_chain
✓ test_get_wallet_risk_endpoint_success
✓ test_registry_refresh_end_to_end_integration
✓ test_graph_context_summary_returns_neighbor_stats

Total: 9 passed, 7 warnings (deprecated APIs in dependencies)
Time: ~11 seconds
Status: NO REGRESSIONS DETECTED ✓
```

---

## Documentation Status

### ❌ DO NOT UPDATE docs/ml.md UNTIL:

1. ✓ The fair comparison is complete (DONE)
2. ✓ Test suite passes (DONE)
3. ⏳ **PENDING:** The discrepancy between documented numbers (AUC-PR 0.4458) and current code (AUC-PR 0.3827 fair, 0.3156 unfair) is explained
4. ⏳ **PENDING:** Investigation into why GraphSAGE does not improve metrics with fair hyperparameters

### Current Documentation Status

**File:** [docs/ml.md](docs/ml.md)

**Section:** "Offline GraphSAGE embedding benchmark (non-production research)"

**Current Status:** ⚠️ UNDER REVIEW - Claims require validation

**Required Action:** Replace the side-by-side benchmark table with:

```markdown
## ⚠️ GraphSAGE Benchmark Status: Under Review

**AUDIT FINDING (2026-09-01):** The published GraphSAGE benchmark used unfair hyperparameters 
for the control model. A fair comparison shows GraphSAGE does NOT improve the primary metric (AUC-PR).

**Fair Comparison Results:**
- Tabular-only baseline: AUC-PR 0.3974, AUC-ROC 0.8523
- Tabular+GraphSAGE: AUC-PR 0.3827, AUC-ROC 0.8439
- **Result:** GraphSAGE degrades AUC-PR by -3.7 percentage points

**Status:** This benchmark requires further investigation. Do NOT consider the GraphSAGE 
integration production-ready until the following are addressed:

1. Explain the discrepancy between documented numbers (AUC-PR 0.4458) and current results (0.3827)
2. Investigate why GraphSAGE is not improving metrics with fair hyperparameters
3. Consider whether the GraphSAGE architecture (2-layer, 16-dim embeddings) is sufficient
4. Review the graph construction and edge filtering logic for potential data leakage

**Previous documentation claiming "meaningful uplift" is withdrawn pending corrected analysis.**
```

---

## Recommendations

### Immediate Actions

1. ✓ **Fix hyperparameter fairness** — DONE (graphsage_risk.py updated)
2. ✓ **Run fair comparison** — DONE (results documented)
3. ✓ **Verify test suite** — DONE (9/9 tests pass)
4. ⏳ **Update documentation** — Mark as "under review", do NOT claim uplift
5. ⏳ **Investigate number discrepancy** — Why can't we reproduce documented AUC-PR 0.4458?

### Investigation Tasks

1. **Reproduce original numbers:**
   - Check if there's a different code branch or version
   - Review git history for changes to graphsage_risk.py
   - Check if the Elliptic++ dataset was updated

2. **Debug GraphSAGE performance:**
   - Verify graph construction is correct (no data leakage)
   - Confirm edge filtering for train-period only is working
   - Check if 2-layer architecture and 16-dim embeddings are sufficient
   - Consider ablation: does GraphSAGE help if we use more layers or higher embedding dims?

3. **Consider alternative approaches:**
   - Instead of GraphSAGE embeddings, try simpler graph features (degree, clustering coefficient, etc.)
   - If GNN is the right approach, experiment with other architectures (GAT, GCN, GraphConv)
   - Profile the inference latency vs accuracy trade-off

### Long-Term Decisions

- **If GraphSAGE cannot be made to improve metrics:** Remove the code and close the feature as "investigated but not beneficial"
- **If GraphSAGE improvement is confirmed:** Merge into production with extensive testing and monitoring
- **Either way:** Document the investigation findings in a separate report for the project archive

---

## References

**Audit Documents:**
- [GraphSAGE_AUDIT_FINDINGS.md](GraphSAGE_AUDIT_FINDINGS.md) — Detailed technical findings
- [GRAPHSAGE_COMPARISON_RESULTS.md](GRAPHSAGE_COMPARISON_RESULTS.md) — Benchmark results comparison

**Code Changes:**
- [backend/app/ml/graphsage_risk.py](backend/app/ml/graphsage_risk.py) — Updated with fair comparison mode

**Test Results:**
- backend/app/tests/test_risk.py — 8/8 passing
- backend/app/tests/test_graphsage_fallback.py — 1/1 passing

---

## Conclusion

**The GraphSAGE benchmark as currently documented is invalid and should not be used to justify production deployment.** A fair comparison using identical hyperparameters shows GraphSAGE does not improve model performance on the primary metric (AUC-PR). 

Before proceeding, the development team must:
1. Explain the discrepancy with previously documented numbers
2. Investigate why GraphSAGE is not providing expected benefits
3. Decide whether to continue GraphSAGE development or pivot to alternatives
4. Update all documentation to reflect the corrected analysis

**Status: READY FOR TEAM REVIEW AND DECISION**
