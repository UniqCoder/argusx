"""
Equivalence check: new app/ml/relative_features.py must reproduce the EXACT
relative-feature values of the validated harness
(app/ml/promotion_experiments.py::build_relative_feature_reference /
add_relative_features) on every row of the test split.

Run from repo root before promotion wiring is trusted.
"""
from __future__ import annotations

import sys
import io

sys.path.insert(0, r"backend")

import numpy as np
import pandas as pd

from app.ml.promotion_experiments import (
    add_relative_features as harness_add, build_relative_feature_reference as harness_fit,
    load_splits,
)
from app.ml.relative_features import (
    apply_relative_features as new_add, fit_relative_reference as new_fit,
)

BUSY = io.StringIO()
old_out, old_err = sys.stdout, sys.stderr
sys.stdout = sys.stderr = BUSY

train_df, val_df, test_df = load_splits()
btc_train = train_df[train_df["chain"].astype(str) == "BTC"].copy()
harness_ref = harness_fit(btc_train)
new_ref = new_fit(btc_train)

# Sanity: same era count + same train_max + same per-bin stats.
print_opts = np.get_printoptions()

results = []
for split_name, frame in (("train", train_df), ("val", val_df), ("test", test_df)):
    h = harness_add(frame, harness_ref)
    n = new_add(frame, new_ref)
    cols = [
        "total_txs_pctile_era", "value_transacted_total_pctile_era",
        "total_txs_z_era", "value_transacted_total_z_era",
    ]
    for col in cols:
        a = h[col].to_numpy(dtype=float)
        b = n[col].to_numpy(dtype=float)
        eq = np.allclose(a, b, rtol=0.0, atol=1e-12)
        maxdiff = float(np.max(np.abs(a - b))) if len(a) else 0.0
        results.append((split_name, col, eq, maxdiff))

sys.stdout, sys.stderr = old_out, old_err

print(f"era bins        : harness={len(harness_ref['total_txs']['bins'])} new={len(new_ref['era_bin_edges']) - 1}")
print(f"train_max_block : harness={max(c.right for c in harness_ref['total_txs']['bins'])} new={new_ref['train_max_block']}")
ok = True
for split_name, col, eq, maxdiff in results:
    mark = "OK " if eq else "FAIL"
    ok &= eq
    print(f"{mark} {split_name:5s} {col:35s} max|diff|={maxdiff:.3e}")
print("OVERALL:", "EQUIVALENT" if ok else "MISMATCH — DO NOT PROMOTE")
sys.exit(0 if ok else 1)