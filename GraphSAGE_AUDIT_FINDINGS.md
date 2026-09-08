# GraphSAGE Benchmark Audit: Critical Methodological Flaws

**Date:** 2026-09-01  
**Status:** FINDINGS DOCUMENTED - FAIR COMPARISON REQUIRED

---

## Executive Summary

The GraphSAGE benchmark comparison in the documentation claims a "meaningful uplift" from adding GraphSAGE embeddings. However, the comparison is **fundamentally unfair** because:

1. **Hyperparameter mismatch**: Control and baseline models trained with different XGBoost parameters
2. **Imbalance handling mismatch**: Baseline uses class-weight adjustment; control doesn't
3. **Threshold selection inconsistency**: Different optimal thresholds selected via same procedure applied to non-identical models
4. **Feature set alignment unclear**: Need to confirm both use identical starting features

This pattern is **exactly consistent with measurement artifact rather than real GraphSAGE benefit.**

---

## Finding #1: XGBoost Hyperparameter Mismatch ❌

### Baseline Model (train.py, lines ~570-583)
**Location:** Production risk model, deployed in `/api/v1/wallets/{address}/risk`

```python
clf = xgb.XGBClassifier(
    n_estimators=150,           # ← 150 trees
    max_depth=5,
    learning_rate=0.06,
    subsample=0.85,
    colsample_bytree=0.85,
    scale_pos_weight=scale_pos_weight,  # ← Dynamic class weighting
    eval_metric="logloss",
    random_state=42,
    tree_method="hist",
)
```

Where `scale_pos_weight` is computed from the training set's class imbalance:
```python
scale_pos_weight = (len(y_train) - y_train.sum()) / max(1, y_train.sum())
```

### Control Model in GraphSAGE Benchmark (graphsage_risk.py, lines ~210-220)
**Location:** Offline benchmark, NOT production

```python
xgb_baseline = xgb.XGBClassifier(
    n_estimators=250,           # ← 250 trees (+67% more than baseline!)
    max_depth=5,
    learning_rate=0.06,
    subsample=0.85,
    colsample_bytree=0.85,
    eval_metric="logloss",
    random_state=42,
    tree_method="hist",
)
xgb_baseline.fit(baseline_X_train, baseline_y_train)
```

**Differences:**
- Baseline: 150 trees + dynamic scale_pos_weight
- Control: 250 trees + NO scale_pos_weight
- This is a **fundamentally different model configuration**

### Impact Assessment

With 250 vs 150 trees and different class-weight handling, the control model is either:
- **Underspecified** (if the larger n_estimators needs the scale_pos_weight to work correctly), or
- **Over-regularized** (if the larger n_estimators overfits without scale_pos_weight)

Either way, **the control baseline is not comparable to the production baseline.**

---

## Finding #2: Threshold Selection Methodology ✓ (Fair)

### Procedure Used in Both Models

Both models use identical threshold-selection logic:

```python
def select_best_threshold(
    y_val: pd.Series,
    y_prob_val: np.ndarray,
    candidate_thresholds: list[float] = [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95],
    max_fpr: float = 0.020,
) -> tuple[float, dict]:
    """
    Select optimal classification threshold on VALIDATION SLICE ONLY (Time steps 30..34).
    Finds threshold that maximizes Recall subject to FPR < max_fpr (2.0%).
    """
```

**This part is fair.** Both models:
- Use the SAME validation slice (time steps 30-34)
- Use the SAME candidate thresholds
- Use the SAME FPR cap (2%)
- Apply the SAME logic: maximize recall subject to FPR constraint

### Different Thresholds Selected

Despite using the same procedure, different thresholds are locked:

| Model | Locked Threshold | Rationale |
|-------|------------------|-----------|
| Baseline (train.py) | 0.90 | Highest recall with FPR < 2% on validation |
| Tabular-only control (graphsage_risk.py) | 0.75 | Highest recall with FPR < 2% on validation |
| Tabular + GraphSAGE (graphsage_risk.py) | 0.50 | Highest recall with FPR < 2% on validation |

**Interpretation issue:** These different thresholds are a SYMPTOM of the models having different capabilities. But because the control model itself is unfair (different hyperparameters), we cannot determine if the threshold difference is real or an artifact.

---

## Finding #3: Feature Set Alignment ✓ (Confirmed Identical)

### Features Used in Both Models

Both models use `FEATURE_COLUMNS` from [backend/app/ml/features.py](backend/app/ml/features.py):

**55 features from Elliptic++ wallets_features.csv:**
- Transaction counts (sender, receiver, total)
- Block heights (first appeared, last appeared, lifetime)
- Value statistics (total, min, max, mean, median for all/sent/received transactions)
- Fee statistics (chain fees, fee ratios)
- Timing statistics (blocks between transactions, input transactions, output transactions)
- Counterparty features (addresses transacted with, multiple transaction addresses)
- Native chain fees (gas price, gas used, bandwidth, energy)

**7 missing-indicator columns (encode structural nullness):**
- `chain_fee_is_missing`, `fee_ratio_is_missing`, `native_fee_is_missing`, `gas_price_is_missing`, `gas_used_is_missing`, `bandwidth_is_missing`, `energy_is_missing`

**Total: 62 features**

### Engineered Graph Features

**NOT present in either model:**
- No `illicit_neighbor_ratio` or similar graph topology features
- Both use raw 62-feature canonical schema
- GraphSAGE model adds learned embeddings ON TOP of these 62 features

**Conclusion:** Feature set is identical. ✓

---

## Finding #4: Reported Performance Metrics

### Side-by-Side Comparison from docs/ml.md

| Variant | Val Threshold | Val Precision | Val Recall | Val FPR | **Test AUC-PR** | **Test AUC-ROC** | Test Precision | Test Recall | Test FPR |
|---------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Tabular-only XGBoost** | 0.75 | 0.7467 | 0.6075 | 0.0179 | **0.3495** | **0.8151** | 0.3357 | 0.4038 | 0.0438 |
| **Tabular + GraphSAGE** | 0.50 | 0.8098 | 0.7676 | 0.0156 | **0.4458** | **0.8858** | 0.3867 | 0.4170 | 0.0363 |
| **Production baseline** | 0.90 | — | — | — | **0.3774** | **0.8463** | 0.4224 | 0.4062 | 0.0305 |

### Problem: Baseline Comparison

The production baseline (trained with 150 trees + scale_pos_weight):
- AUC-PR: 0.3774
- AUC-ROC: 0.8463

The tabular-only control in the GraphSAGE benchmark:
- AUC-PR: 0.3495 (⚠️ **worse than production baseline**)
- AUC-ROC: 0.8151 (⚠️ **worse than production baseline**)

**Why is the control worse?**
- Different hyperparameters (250 trees instead of 150)
- Missing class-weight adjustment (scale_pos_weight)
- Resulting in **unfair negative bias** against the control
- Making GraphSAGE appear to "lift" the control back toward the real baseline

---

## Finding #5: Windows Shell Quoting Issue

### Current Issue in test_graphsage_fallback.py

The test file exists but is not run as part of the full suite because the invocation has shell quoting problems on Windows:

**Expected issue:** Running `pytest` from PowerShell with quoted test file paths fails with CRLF/LF line ending issues or Windows path escaping.

**Impact:** The full risk test suite is NOT validated, creating a gap in test coverage.

---

## Corrective Actions Required

### Phase 1: Fair Comparison (Immediate)

1. **Create corrected benchmark** with identical hyperparameters:
   - Both models: n_estimators=150 (not 250)
   - Both models: scale_pos_weight=computed (not omitted)
   - Both models: identical threshold procedure (already done, keep it)
   - Both models: identical feature set (already done, keep it)

2. **Re-run benchmark** with fair conditions and report corrected numbers

3. **Document the finding** that control was unfair and report actual GraphSAGE uplift

### Phase 2: Test Suite Validation (Immediate)

1. Fix Windows shell quoting in test invocation
2. Run full test_risk.py suite
3. Verify no regressions

### Phase 3: Documentation Update (After validation)

1. Update docs/ml.md to clarify:
   - Original benchmark used unfair control
   - Corrected numbers replace the original comparison
   - Whether GraphSAGE uplift is real or was an artifact

2. Do NOT claim "verified uplift" until this fair comparison is complete

---

## Recommended Action: Run Audit Verification Script

```bash
# 1. Run corrected GraphSAGE benchmark (new code with fair hyperparameters)
python -m app.ml.graphsage_risk --fair-comparison

# 2. Run full risk test suite
& "python.exe" -m pytest backend/app/tests/test_risk.py -v

# 3. Report corrected metrics
```

---

## Conclusion

**The current "uplift" framing in docs/ml.md is not yet justified because:**

1. Control model used different XGBoost hyperparameters than production baseline
2. Control model omitted scale_pos_weight class-weight adjustment
3. Control model underperforms production baseline (AUC-PR 0.3495 vs 0.3774)
4. GraphSAGE model's improvement might be recovering from an artificially weakened control, not a real benefit

**Before accepting the GraphSAGE work as production-ready, a fair apples-to-apples comparison is MANDATORY.**

---

## Files Involved

- [backend/app/ml/graphsage_risk.py](backend/app/ml/graphsage_risk.py) — Benchmark code with hyperparameter mismatch
- [backend/app/ml/train.py](backend/app/ml/train.py) — Production baseline (correct hyperparameters)
- [backend/app/ml/features.py](backend/app/ml/features.py) — Feature schema
- [docs/ml.md](docs/ml.md) — Documentation claiming "verified uplift"
- [backend/ML_RISK_MODEL_STATUS.md](backend/ML_RISK_MODEL_STATUS.md) — Status report with benchmark numbers
- [backend/app/tests/test_risk.py](backend/app/tests/test_risk.py) — Risk test suite
- [backend/app/tests/test_graphsage_fallback.py](backend/app/tests/test_graphsage_fallback.py) — GraphSAGE-specific test
