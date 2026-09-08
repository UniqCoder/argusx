# Incident: Label Leak in Graph Feature Snapshot (2026-09-06)

## Summary

A self-referential label leak was discovered in `snapshot_graph_features.py` on 2026-09-06 during a post-deployment audit of the graph-feature retrain. The leak caused every test-split illicit wallet to receive `shortest_path_to_known_illicit = 0` by reading its own gold label, inflating BTC test AUC-PR from an honest 0.4665 to a spurious 1.0. The leak was introduced on 2026-09-06 in the same session that built the graph feature snapshot, and was reverted the same day after the audit. No live production inference was affected — the pre-graph-fix model was restored to production before any live scoring ran on the leaked artifact.

## Root cause

`snapshot_graph_features.py:96` built `illicit_t` from the **full** `wallets_classes.csv` (all splits, class==1), not restricted to the train split. Line 168: `if addr in illicit_t: shortest = 0` — every test-split illicit wallet self-flagged distance 0 at its own era.

The code was:

```python
# BROKEN — seeded from ALL splits (train + val + test)
illicit_t = set(classes.loc[classes["class"] == 1, "address"])
```

This meant a test wallet's own gold label was available to the snapshot builder, and the self-check at line 168 short-circuited `shortest` to 0. The feature became a direct encoding of the label, not a topological distance.

## Oracle proof

- **4,938 / 4,938** BTC test illicit wallets had `shortest == 0`
- **0 / 90,012** BTC test licit wallets had `shortest == 0`
- A single rule `shortest == 0 → illicit` = 100% precision and recall (TP 4938, FP 0, FN 0, TN 90012)

## A/B results

| Variant | BTC AUC-PR | @0.5 P | @0.5 R | F1 |
|---|---|---|---|---|
| Leaky model + live graph features | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Leaky model + zeroed graph columns | 0.1057 | 0.0524 | 0.9998 | 0.0996 |
| Pre-graph-fix + corrected snapshot | 0.4574 | 0.6258 | 0.3248 | 0.4277 |
| Pre-graph-fix baseline (graph cols dead) | **0.4665** | 0.5747 | 0.3910 | 0.4654 |

The A/B confirms:
- The XGBoost model allocated capacity to the leaked `shortest_path` column, producing 1.0 on test.
- When graph columns are zeroed, the leaky model degrades to 0.1057 — the model had learned to rely on the leaked feature.
- The honest model (0.4665) was unaffected because graph columns were constant 0 in its training.

## ETH negative control

ETH rows get `fillna(0)` in the snapshot pipeline → no oracle mechanism → ETH AUC-PR stays at 0.9667, confirming the leak was BTC-specific and caused by the `illicit_t` seed.

## Resolution

1. **Leaky artifact archived:** `risk_model.leaky_graph92.joblib` + `risk_model_metrics.leaky_graph92.json` retained as cautionary artifacts.
2. **Pre-graph-fix model restored:** `risk_model.pre_graph_fix.joblib` → `risk_model.joblib`; `risk_model_metrics.pre_graph_fix.json` → `risk_model_metrics.json`; `relative_features_reference.pre_graph_fix.json` → `relative_features_reference.json`.
3. **Backend restarted** with the restored artifact.
4. **Live verified:** Garantex 1.0 (sanctions override), Binance hot 0.037 (low), all FP re-checks pass.
5. **No retrain performed.** The pre-graph-fix model (BTC AUC-PR 0.4665, locked threshold 0.70) is the accepted production model.

## Protocol fix (snapshot rebuild)

`snapshot_graph_features.py` was rewritten:

- **Train-split-only seeding:** `illicit_t = class==1 ∩ train.csv addresses` (not the full dataset).
- **Self-excluded:** `shortest` = distance to the **nearest OTHER** known-illicit wallet (capped at 6). A wallet cannot flag itself.
- **Memory-lean:** Rewritten with int-id mapping + scipy CSR adjacency (peak ~1.5GB vs 4.5GB before).
- **Verified:** `verify_snapshot.py` asserts `shortest_path ∈ {1,2,3,4,5,6}` globally (sp=0 count = 0). 8/8 spot-checks pass, 0 future-data leaks.
- **Archived leaky CSV:** `graph_features_snapshot.leaky.csv` retained; `graph_features_snapshot.csv` rebuilt with corrected semantics (822,942 rows).

## Graph features: zero real signal finding

Two independent attempts to add graph features to the model resolved to the same conclusion:

1. **First attempt (raw/processed mismatch):** Graph features had a different semantic than training-time features → no useful signal.
2. **Second attempt (self-referential leak):** Graph features encoded the label directly → spurious 1.0 → degraded to 0.1057 when zeroed.

The corrected snapshot (AUC-PR 0.4574) is within noise of the baseline (0.4665). **Graph features add zero real signal on this dataset's offline metric.** The infrastructure is retained for live inference observability (neighbor counts, shortest path surfaced in evidence output) but is NOT in the active production model's feature set.

## Decision

**Stop at pre-graph-fix model. Do NOT retrain.** Graph feature infrastructure retained for live observability only. The production model uses 92 features (72 tabular + 4 relative + 16 GraphSAGE), with graph columns constant 0 for BTC rows.

## Enrichment independence analysis

The live enrichment task (`illicit_enrichment.py`) sets `illicit=true` on Neo4j Wallet nodes from two sources:

### SOURCE 1: `KNOWN_ILLICIT_WALLETS` (curated, independent)

`known_illicit.py:31-44` — Two hardcoded addresses:
- Garantex BTC (`3Lpoy53K625zVeE47ZasiG5jGkAxJ27kh1`) — OFAC-designated
- Lazarus Group proxy TRON (`TLa2f6VPqDMsaxQVj7FSrsDjjQuT5Zox1g`) — documented

This is an immutable constant. No write path exists to modify it from code, model output, or database. **Fully independent of model output.**

### SOURCE 2: `_query_case_blocked_addresses` (frozen cases, NOT fully independent)

`illicit_enrichment.py:34-46` — Reads wallets linked to PostgreSQL cases with `status='frozen'`. The `frozen` status requires two manual analyst actions:
1. `POST /api/v1/cases` — create a case and link wallet IDs
2. `PATCH /api/v1/cases/{id}` — transition status to `frozen` (validated by state machine)

**No automated path exists** from model scores to case creation or case freezing. But the data dependency is closed via human mediation:

```
ML model score → /check-wallet → alert → analyst sees alert
→ analyst POSTs /api/v1/cases (links wallet)
→ analyst PATCHes case to frozen
→ enrich_illicit_flags_task reads frozen cases
→ SET w.illicit = true in Neo4j
→ live_graph_features.py reads neighbor.illicit
→ ML model scores neighbors of newly-frozen wallets differently
[LOOP CLOSES via human gate]
```

This is an **open architectural risk**, not a data leak in the same class as the original self-referential shortest_path leak. The human gate prevents automated drift, but once a case is frozen, the enrichment is fully automated and feeds back into the model's feature space.

### No automated regression guard

- `verify_snapshot.py` train-split-only + self-exclusion invariant: **offline-only**, not enforced in the live serving path.
- `live_graph_features.py:220` allows `shortest_path=0` for self-illicit wallets (the **opposite** of verify_snapshot.py's `sp >= 1` invariant) — this is by design for live enrichment but creates a training/serving asymmetry.
- No CI, no pytest, no beat schedule, no startup check runs verify_snapshot.
- No test verifies enrichment source provenance or graph feature independence.

## Garantex short-circuit

The Garantex live inference result (risk 1.0, critical) is **100% from the sanctions override**, not from ML or graph features:

```
/wallets/3Lpoy53K.../risk?chain=BTC
  → evaluate_wallet_risk()                    [risk_service.py:44]
  → sanctions_service.lookup_sanctioned()     [risk_service.py:57] ← FIRST THING
  → MATCH in sanctions_seed.json (OFAC)       → return immediately
  → build_sanctions_override_response()       [risk_service.py:66]
  → RiskResponse(risk_score=1.0,              [sanctions_service.py:131]
                  risk_tier=critical,
                  risk_source="sanctions_override")
```

The model never runs. No graph queries. No feature vector. No `predict_proba`. The 1.0 is hardcoded at `sanctions_service.py:131` and returned at `risk_service.py:66` before any downstream code executes.

**No leak-adjacent path exists for Garantex.** Even if graph features were queried (they are not), the self-referential pattern would set `shortest_path=0` for Garantex (it IS illicit in Neo4j), but this never reaches the model.

## Open risks

1. **Enrichment drift via frozen cases (SOURCE 2):** A human analyst who looks at the model's risk score and then freezes a case based on that judgment creates a path from model output → enrichment set → graph features → future model scores. The loop is gated by two manual actions but the data dependency is closed. **Mitigation:** restrict enrichment to SOURCE 1 only, or add a provenance check that prevents model-derived cases from feeding back into the enrichment set.
2. **Training/serving asymmetry:** `shortest_path` domain is `{1..6}` in training but `{0..6}` in live serving. This is by design (live enrichment flags known-illicit wallets) but means the model sees `shortest_path=0` at serving time for enriched wallets, which never occurred in training. **Impact:** currently minimal (only 2-3 enriched wallets exist), but would grow if the enrichment set expands.
3. **No automated regression guard:** The snapshot invariant (`sp >= 1`, train-split-only seeding) is not enforced in any CI/test/deploy pipeline. A code change to `snapshot_graph_features.py` or `live_graph_features.py` could reintroduce the leak without detection.

## Archived artifacts

| File | Purpose |
|---|---|
| `risk_model.leaky_graph92.joblib` | Leaky model artifact (trained on leaked graph features) |
| `risk_model_metrics.leaky_graph92.json` | Metrics for the leaky model |
| `graph_features_snapshot.leaky.csv` | Snapshot CSV built with full-dataset seeding (pre-fix) |
| `risk_model.pre_graph_fix.joblib` | Backup of pre-graph-fix model (still the production artifact) |
| `risk_model_metrics.pre_graph_fix.json` | Backup of pre-graph-fix metrics |
| `relative_features_reference.pre_graph_fix.json` | Backup of pre-graph-fix relative features reference |
