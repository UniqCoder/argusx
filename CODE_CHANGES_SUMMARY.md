# Code Changes: GraphSAGE Benchmark Fix

**File Modified:** `backend/app/ml/graphsage_risk.py`  
**Date:** 2026-09-01  
**Purpose:** Add fair comparison mode with identical hyperparameters to production baseline

---

## Change 1: Updated `compute_graph_embedding_metrics()` function signature

### Before (Line 156-160)
```python
def compute_graph_embedding_metrics(
    graph: Data,
    embeddings: np.ndarray,
    feature_df: pd.DataFrame,
    threshold_candidates: list[float] | None = None,
) -> dict[str, Any]:
    """Train XGBoost on tabular-only and tabular+embedding features using the same threshold scan."""
```

### After (Line 156-170)
```python
def compute_graph_embedding_metrics(
    graph: Data,
    embeddings: np.ndarray,
    feature_df: pd.DataFrame,
    threshold_candidates: list[float] | None = None,
    use_fair_hyperparameters: bool = True,  # ← NEW PARAMETER
) -> dict[str, Any]:
    """Train XGBoost on tabular-only and tabular+embedding features using the same threshold scan.
    
    Args:
        use_fair_hyperparameters: If True, use identical hyperparameters to the production baseline
                                  (n_estimators=150, scale_pos_weight computed from training set).
                                  If False, use the original unfair comparison.
    """
```

---

## Change 2: Added class-weight computation and hyperparameter selection logic

### Before (Line 191-220)
```python
    emb_train = embeddings[train_idx]
    emb_val = embeddings[val_idx]
    emb_test = embeddings[test_idx]

    xgb_baseline = xgb.XGBClassifier(
        n_estimators=250,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="logloss",
        random_state=42,
        tree_method="hist",
    )
    xgb_baseline.fit(baseline_X_train, baseline_y_train)
    baseline_val_prob = xgb_baseline.predict_proba(baseline_X_val)[:, 1]
    baseline_thresh, baseline_summary = select_best_threshold(pd.Series(baseline_y_val), baseline_val_prob, threshold_candidates)

    xgb_embed_X_train = np.hstack([baseline_X_train, emb_train])
    xgb_embed_X_val = np.hstack([baseline_X_val, emb_val])
    xgb_embed_X_test = np.hstack([baseline_X_test, emb_test])

    xgb_embed = xgb.XGBClassifier(
        n_estimators=250,
        max_depth=5,
        learning_rate=0.06,
        subsample=0.85,
        colsample_bytree=0.85,
        eval_metric="logloss",
        random_state=42,
        tree_method="hist",
    )
    xgb_embed.fit(xgb_embed_X_train, baseline_y_train)
```

### After (Line 191-238)
```python
    emb_train = embeddings[train_idx]
    emb_val = embeddings[val_idx]
    emb_test = embeddings[test_idx]

    # ← NEW: Compute class-weight adjustment for imbalance
    scale_pos_weight = (len(baseline_y_train) - baseline_y_train.sum()) / max(1, baseline_y_train.sum())
    
    # ← NEW: Select XGBoost hyperparameters based on fairness requirement
    n_estimators = 150 if use_fair_hyperparameters else 250
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
        xgb_kwargs["scale_pos_weight"] = scale_pos_weight

    xgb_baseline = xgb.XGBClassifier(**xgb_kwargs)
    xgb_baseline.fit(baseline_X_train, baseline_y_train)
    baseline_val_prob = xgb_baseline.predict_proba(baseline_X_val)[:, 1]
    baseline_thresh, baseline_summary = select_best_threshold(pd.Series(baseline_y_val), baseline_val_prob, threshold_candidates)

    xgb_embed_X_train = np.hstack([baseline_X_train, emb_train])
    xgb_embed_X_val = np.hstack([baseline_X_val, emb_val])
    xgb_embed_X_test = np.hstack([baseline_X_test, emb_test])

    xgb_embed = xgb.XGBClassifier(**xgb_kwargs)
    xgb_embed.fit(xgb_embed_X_train, baseline_y_train)
```

---

## Change 3: Updated `run_offline_graphsage_benchmark()` function

### Before (Line 303-309)
```python
def run_offline_graphsage_benchmark(data_dir: str | None = None) -> dict[str, Any]:
    """Convenience entry point for the offline GraphSAGE benchmark."""
    data_dir = data_dir or get_data_dir()
    feature_df, graph, _, train_edge_index = load_labeled_wallet_graph(data_dir)
    model = train_graphsage(graph, train_edge_index=train_edge_index)
    embeddings = extract_all_embeddings(model, graph)
    report = compute_graph_embedding_metrics(graph, embeddings, feature_df)
    report["dataset"] = {"data_dir": data_dir, "wallets": int(len(feature_df)), "train_nodes": int(graph.train_mask.sum()), "val_nodes": int(graph.val_mask.sum()), "test_nodes": int(graph.test_mask.sum())}
    return report
```

### After (Line 303-324)
```python
def run_offline_graphsage_benchmark(data_dir: str | None = None, use_fair_hyperparameters: bool = True) -> dict[str, Any]:
    """Convenience entry point for the offline GraphSAGE benchmark.
    
    Args:
        data_dir: Path to the Elliptic++ dataset directory.
        use_fair_hyperparameters: If True, use identical hyperparameters to production baseline
                                  (n_estimators=150, scale_pos_weight). If False, use the 
                                  original unfair comparison (n_estimators=250, no scale_pos_weight).
                                  Default is True for fair comparison.
    """
    data_dir = data_dir or get_data_dir()
    feature_df, graph, _, train_edge_index = load_labeled_wallet_graph(data_dir)
    model = train_graphsage(graph, train_edge_index=train_edge_index)
    embeddings = extract_all_embeddings(model, graph)
    report = compute_graph_embedding_metrics(graph, embeddings, feature_df, use_fair_hyperparameters=use_fair_hyperparameters)
    report["dataset"] = {"data_dir": data_dir, "wallets": int(len(feature_df)), "train_nodes": int(graph.train_mask.sum()), "val_nodes": int(graph.val_mask.sum()), "test_nodes": int(graph.test_mask.sum())}
    report["hyperparameter_mode"] = "fair" if use_fair_hyperparameters else "original_unfair"
    return report
```

---

## Change 4: Added command-line interface (main block)

### Before (Line 311-313)
```python
if __name__ == "__main__":
    benchmark = run_offline_graphsage_benchmark()
    print(json.dumps(benchmark, indent=2, default=str))
```

### After (Line 326-351)
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
        print("  - n_estimators: 150")
        print("  - scale_pos_weight: computed from training set imbalance")
    else:
        print("[ORIGINAL MODE] Using unfair hyperparameters as originally coded...")
        print("  - n_estimators: 250")
        print("  - scale_pos_weight: NOT used")
    print()
    
    benchmark = run_offline_graphsage_benchmark(use_fair_hyperparameters=use_fair)
    print(json.dumps(benchmark, indent=2, default=str))
```

---

## Summary of Changes

| Change | Impact | Reason |
|--------|--------|--------|
| Added `use_fair_hyperparameters` parameter | Allows mode selection | Enable fair comparison option |
| Compute `scale_pos_weight` from training set | Matches production baseline | Same class imbalance handling |
| Dynamic `n_estimators` selection | 150 for fair, 250 for unfair | Fair mode matches production (150 trees) |
| Added report["hyperparameter_mode"] tracking | Documents which mode was used | Prevents silent mode confusion |
| Added argparse CLI | User-friendly mode selection | Command-line control without code edits |

---

## Usage

### Run Fair Comparison (Recommended)
```bash
cd c:\vs code\SIH\backend
python app\ml\graphsage_risk.py
```

Output:
```
[FAIR COMPARISON MODE] Using identical hyperparameters to production baseline...
  - n_estimators: 150
  - scale_pos_weight: computed from training set imbalance

[VALIDATION SLICE THRESHOLD SCAN (Time Steps 30..34)]
 Threshold |  Precision |     Recall |        FPR | FPR < 2%
...
```

### Run Unfair Comparison (For Documentation Only)
```bash
python app\ml\graphsage_risk.py --unfair
```

Output:
```
[ORIGINAL MODE] Using unfair hyperparameters as originally coded...
  - n_estimators: 250
  - scale_pos_weight: NOT used

[VALIDATION SLICE THRESHOLD SCAN (Time Steps 30..34)]
 Threshold |  Precision |     Recall |        FPR | FPR < 2%
...
```

---

## Testing

All tests pass with the changes:

```bash
# Risk tests (8 tests)
pytest app/tests/test_risk.py -v
# ======================== 8 passed ========================

# GraphSAGE fallback test (1 test)
pytest app/tests/test_graphsage_fallback.py -v
# ======================== 1 passed ========================

# Total: 9/9 tests pass, no regressions
```

---

## Backward Compatibility

The changes are backward compatible:
- ✓ Default behavior (`use_fair_hyperparameters=True`) is new, correct behavior
- ✓ Old unfair mode still available via `--unfair` flag for documentation/comparison
- ✓ No changes to production risk model (train.py remains untouched)
- ✓ No changes to model serialization/loading
- ✓ All existing tests continue to pass
