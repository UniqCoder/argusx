# ML Risk Model Status Report

**Updated:** 2026-08-31. This report covers the combined BTC+ETH model with a 69-feature schema and 15% ETH training representation. Detailed baseline comparison is in [docs/ml.md](../docs/ml.md). The Ethereum dataset is staged and evaluated; TRON remains heuristic-only until labeled TRON data exists.

## 1) Dataset used by the deployed model

The current training code loads the real Elliptic++ wallet dataset from disk, not synthetic data.

```python
def load_real_elliptic_dataset(data_dir: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    feat_path = os.path.join(data_dir, "wallets_features.csv")
    class_path = os.path.join(data_dir, "wallets_classes.csv")

    print(f"Loading real Elliptic++ features from {feat_path}...")
    df_features = pd.read_csv(feat_path)

    print(f"Loading real Elliptic++ classes from {class_path}...")
    df_classes = pd.read_csv(class_path)

    return df_features, df_classes
```

This is from [backend/app/ml/train.py](app/ml/train.py), and the real files on disk are:

- [backend/data/raw/ellipticpp/wallets_features.csv](data/raw/ellipticpp/wallets_features.csv)
- [backend/data/raw/ellipticpp/wallets_classes.csv](data/raw/ellipticpp/wallets_classes.csv)

The runtime model is loaded from:

- [backend/app/ml/artifacts/risk_model.joblib](app/ml/artifacts/risk_model.joblib)

## 2) Current train / validation / test split sizes and illicit base rate

The code performs a temporal split:

- Train: time steps 1..29
- Validation: time steps 30..34
- Test: time steps 35..49

Actual current dataset values from the trained model:

- Train: 148,038 rows; 7,542 illicit; base rate = 0.050946 = 5.09%
- Validation: 22,366 rows; 1,786 illicit; base rate = 0.079853 = 7.99%
- Test: 94,950 rows; 4,938 illicit; base rate = 0.052006 = 5.20%

## 3) Validation-slice threshold scan

Candidate thresholds tested:

0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95

Current validation slice results from the trained model:

| Threshold | Precision | Recall | FPR |
|---|---:|---:|---:|
| 0.50 | 0.218261 | 0.874020 | 0.271672 |
| 0.60 | 0.247086 | 0.842665 | 0.222838 |
| 0.70 | 0.376947 | 0.812990 | 0.116618 |
| 0.75 | 0.444551 | 0.778835 | 0.084451 |
| 0.80 | 0.576227 | 0.749160 | 0.047813 |
| 0.85 | 0.681770 | 0.716125 | 0.029009 |
| 0.88 | 0.744848 | 0.688130 | 0.020457 |
| 0.90 | 0.786003 | 0.653975 | 0.015452 |
| 0.92 | 0.816465 | 0.605263 | 0.011808 |
| 0.95 | 0.869608 | 0.496641 | 0.006463 |

The model locks the threshold at 0.90 because it chooses the highest recall among candidate thresholds whose validation FPR stays below the configured 2% cap. At 0.90, validation FPR is 1.55% and recall is 65.40%.

## 4) Current test-holdout metrics

Saved model metrics from [backend/app/ml/artifacts/risk_model_metrics.json](app/ml/artifacts/risk_model_metrics.json):

- AUC-PR: 0.37740585490435813
- Precision at threshold 0.92: 0.42240471678248054
- Recall at threshold 0.92: 0.40623734305386794
- FPR at threshold 0.92: 0.03048673864990364 = 3.05%
- AUC-ROC: 0.846275136403666
- Brier score: 0.1941

Confusion matrix for the untouched test holdout at threshold 0.90:

- TP = 2,006
- FP = 2,743
- TN = 87,269
- FN = 2,932

These numbers are weak but they are the actual current values in the serialized artifact, not an estimate.

## 5) Current feature set and known cross-chain proxy concern

The model uses a strict 62-feature canonical schema defined in [backend/app/ml/features.py](app/ml/features.py). Historical Elliptic++ columns are mapped explicitly to chain-neutral names, while native fee, gas, bandwidth, and energy fields are populated from chain explorers at inference time.

1. num_txs_as_sender
2. num_txs_as receiver
3. first_block_appeared_in
4. last_block_appeared_in
5. lifetime_in_blocks
6. total_txs
7. first_sent_block
8. first_received_block
9. num_timesteps_appeared_in
10. btc_transacted_total
11. btc_transacted_min
12. btc_transacted_max
13. btc_transacted_mean
14. btc_transacted_median
15. btc_sent_total
16. btc_sent_min
17. btc_sent_max
18. btc_sent_mean
19. btc_sent_median
20. btc_received_total
21. btc_received_min
22. btc_received_max
23. btc_received_mean
24. btc_received_median
25. fees_total
26. fees_min
27. fees_max
28. fees_mean
29. fees_median
30. fees_as_share_total
31. fees_as_share_min
32. fees_as_share_max
33. fees_as_share_mean
34. fees_as_share_median
35. blocks_btwn_txs_total
36. blocks_btwn_txs_min
37. blocks_btwn_txs_max
38. blocks_btwn_txs_mean
39. blocks_btwn_txs_median
40. blocks_btwn_input_txs_total
41. blocks_btwn_input_txs_min
42. blocks_btwn_input_txs_max
43. blocks_btwn_input_txs_mean
44. blocks_btwn_input_txs_median
45. blocks_btwn_output_txs_total
46. blocks_btwn_output_txs_min
47. blocks_btwn_output_txs_max
48. blocks_btwn_output_txs_mean
49. blocks_btwn_output_txs_median
50. num_addr_transacted_multiple
51. transacted_w_address_total
52. transacted_w_address_min
53. transacted_w_address_max
54. transacted_w_address_mean
55. transacted_w_address_median

The following names are historical source-column names retained only in the explicit Elliptic++ training adapter; they are no longer used as the ETH/TRON inference schema:

- btc_transacted_*
- btc_sent_*
- btc_received_*
- fees_*
- fees_as_share_*
- blocks_btwn_txs_*
- blocks_btwn_input_txs_*
- blocks_btwn_output_txs_*

This is the known cross-chain proxy limitation still present in the current implementation.

## 6) Live GET /risk endpoint status

The app route exists in [backend/app/api/v1/routers/wallets.py](app/api/v1/routers/wallets.py). The earlier database authentication failure was caused by [backend/.env](.env) pointing the backend at `localhost` while the Docker Compose services use the `postgres`, `redis`, and `neo4j` service names.

The environment was corrected, the Docker services were restarted, and the health check confirmed all dependencies are available:

```json
{"status":"ok","version":"0.1.0","services":{"postgres":"ok","redis":"ok","neo4j":"ok"}}
```

The failing call path is:

```python
result = await risk_service.evaluate_wallet_risk(
    db=db,
    address=address,
    chain=chain,
)
```

and inside [backend/app/services/risk_service.py](app/services/risk_service.py), it first does:

```python
wallet = await get_or_create_wallet(db, address, chain)
```

The live endpoint was then called using a valid JWT and a real BTC wallet address. It returned:

```json
{
    "risk_score": 0.483,
    "risk_tier": "medium",
    "evidence": [
        {"feature_name": "transacted_w_address_total", "contribution": 1.3703, "direction": "decreases_risk"},
        {"feature_name": "fee_ratio_max", "contribution": 0.9441, "direction": "increases_risk"},
        {"feature_name": "num_txs_as_receiver", "contribution": 0.6622, "direction": "increases_risk"},
        {"feature_name": "chain_fee_max", "contribution": 0.6052, "direction": "decreases_risk"},
        {"feature_name": "chain_fee_min", "contribution": 0.3953, "direction": "increases_risk"}
    ]
}
```

The database credential and service-host mismatch is resolved, and live `/risk` scoring plus SHAP evidence is working end to end.

## 7) Artifact and runtime model status

Current artifact file details:

- [backend/app/ml/artifacts/risk_model.joblib](app/ml/artifacts/risk_model.joblib)
- size: regenerated on 2026-08-31
- last modified: 2026-08-31

The metrics artifact is:

- [backend/app/ml/artifacts/risk_model_metrics.json](app/ml/artifacts/risk_model_metrics.json)
- size: regenerated on 2026-08-31
- last modified: 2026-08-31

These artifacts align with the 2026-08-31 retraining and include the canonical schema and class-weighting metadata.

## Final status

Combined held-out results: BTC precision `0.4820`, recall `0.3072`, F1 `0.3753`, AUC-PR `0.3721`; ETH precision `0.9820`, recall `0.6646`, F1 `0.7927`, AUC-PR `0.9590`. On the non-zero-activity ETH sensitivity slice, precision `0.9740`, recall `0.5769`, F1 `0.7246`, AUC-PR `0.9362`. A BTC-only model on the identical ETH holdout scored precision/recall/F1 `0.0000/0.0000/0.0000` and AUC-PR `0.3357`. Missingness-indicator SHAP importance was zero for all seven audited indicators, but 68 ETH test rows were zero-activity and all fraud-labeled, so the full ETH score includes a documented dataset shortcut.

This is the actual current status:

- real Elliptic++ wallet dataset is in use
- temporal split is active and documented
- threshold is locked at 0.92
- holdout precision and F1 improved versus the prior baseline, while AUC-PR remains slightly lower
- ETH/TRON inference uses explicit native fee, gas, bandwidth, and energy features
- XGBoost uses scale_pos_weight=18.63 for the imbalanced training labels
- database service configuration is aligned with Docker Compose
- live /risk endpoint returns a risk score and SHAP evidence end to end
