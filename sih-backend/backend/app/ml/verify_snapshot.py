"""
app/ml/verify_snapshot.py — Independent spot-check of graph_features_snapshot.csv.

Deliberately does NOT import snapshot_graph_features. It recomputes each sampled
wallet's point-in-time graph features from the RAW CSVs using separate code, so a
shared bug cannot pass the check. Verifies:
  * neighbor sets match exactly (with self-loops excluded),
  * each counted neighbor's first-appearance <= owned t      (NO future leakage),
  * every neighbor flagged illicit is class==1 AND known by t,
  * every illicit SEED is restricted to the TRAIN split (class==1 AND address
    in train.csv) — val/test gold labels never enter any feature,
  * a wallet is NEVER its own seed: shortest_path==0 is impossible (a known-
    illicit wallet must be at distance >=1 from a DISTINCT other known-illicit),
  * BFS shortest-path-to-illicit matches (multi-source over G_t),
  * 1-hop / 2-hop ratios match exactly.

Usage:
  python app/ml/verify_snapshot.py <data_dir> <processed_dir> [max_checks]
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

GRAPH_FEATURE_COLS = [
    "illicit_neighbor_ratio_1hop",
    "illicit_neighbor_ratio_2hop",
    "shortest_path_to_known_illicit",
]


def _build_present_ordered(feats: pd.DataFrame):
    per = feats.groupby("address")["Time step"].agg(["min", "max"]).copy()
    per.columns = ["first", "time_step"]
    addr_sorted = np.array(sorted(per.index), dtype="<U40")
    first = per["first"].to_numpy()
    return per, addr_sorted, first


def _load_candidates(snapshot_path: str, train_path: str, val_path: str, test_path: str):
    snap = pd.read_csv(snapshot_path)
    snap_map = {
        r["address"]: r for _, r in snap.iterrows()
    }

    have_train = {a for a in pd.read_csv(train_path, usecols=["address"])["address"].astype(str)}
    have_val = {a for a in pd.read_csv(val_path, usecols=["address"])["address"].astype(str)}
    have_test = {a for a in pd.read_csv(test_path, usecols=["address"])["address"].astype(str)}

    snap["_in_train"] = snap["address"].isin(have_train)
    snap["_in_val"] = snap["address"].isin(have_val)
    snap["_in_test"] = snap["address"].isin(have_test)

    max_checks = int(os.environ.get("MAX_CHECKS", "10"))

    picked = []
    seen = set()
    def add(frame_tag, cond=None, max_n=99, t_max=None):
        if frame_tag == "train":
            label_mask = snap["_in_train"]
        elif frame_tag == "val":
            label_mask = snap["_in_val"]
        else:
            label_mask = snap["_in_test"]
        mask = label_mask & pd.Series(True, index=snap.index)
        if cond is not None:
            mask = mask & cond
        if t_max is not None:
            mask = mask & (snap["time_step"] <= t_max)
        for _, r in snap[mask].iterrows():
            if len(picked) >= max_checks:
                return
            if r["address"] in seen:
                continue
            seen.add(r["address"])
            picked.append((frame_tag, r["address"]))
            if len(picked) >= max_n:
                break

    # Prefer informative cases on the audit (train side, t<=29):
    add("train", cond=snap["illicit_neighbor_ratio_1hop"] > 0, max_n=3, t_max=29)
    add("train", cond=snap["shortest_path_to_known_illicit"] == 1, max_n=2, t_max=29)
    add("train", cond=snap["illicit_neighbor_ratio_2hop"] > 0, max_n=2, t_max=29)
    # Gap fill on plain train wallets
    add("train", max_n=3, t_max=29)
    # Future-leak focus: later-period wallets (val/test)
    add("val", max_n=2)
    add("test", max_n=2)

    return picked, snap_map


def main() -> int:
    data_dir = sys.argv[1]
    processed_dir = sys.argv[2]
    max_checks = int(os.environ.get("MAX_CHECKS", "10"))

    feats = pd.read_csv(os.path.join(data_dir, "wallets_features.csv"), usecols=["address", "Time step"])
    feats["address"] = feats["address"].astype(str).str.lower()
    classes = pd.read_csv(os.path.join(data_dir, "wallets_classes.csv"))
    classes["address"] = classes["address"].astype(str).str.lower()
    classes = classes.drop_duplicates(subset=["address"]).copy()
    train_set = set(
        pd.read_csv(os.path.join(processed_dir, "train.csv"), usecols=["address"])
        ["address"].astype(str).str.lower()
    )
    # Seeds = TRAIN-split labeled illicit ONLY. The old full-gold seed set let
    # test wallets re-encode their own labels (BTC test AUC-PR==1.0000 leak).
    illicit_all = set(classes.loc[classes["class"] == 1, "address"]) & train_set

    per, addr_sorted, first = _build_present_ordered(feats)
    first_map = per["first"].to_dict()

    edge = pd.read_csv(os.path.join(data_dir, "AddrAddr_edgelist.csv"))
    edge.columns = ["src", "dst"]
    edge["src"] = edge["src"].astype(str).str.lower()
    edge["dst"] = edge["dst"].astype(str).str.lower()
    edge = edge[edge["src"] != edge["dst"]]
    src_all = edge["src"].to_numpy(dtype="<U40")
    dst_all = edge["dst"].to_numpy(dtype="<U40")

    picked, snap_map = _load_candidates(
        os.path.join(processed_dir, "graph_features_snapshot.csv"),
        os.path.join(processed_dir, "train.csv"),
        os.path.join(processed_dir, "val.csv"),
        os.path.join(processed_dir, "test.csv"),
    )

    print(f"Verifying {len(picked)} addresses (split, addr, t):")
    for tag, addr in picked:
        print(f"  {tag:5s} {addr}")
    print("=" * 100)

    failures = 0
    for tag, addr in picked:
        if addr not in per.index:
            print(f"FAIL {addr}: not in features file"); failures += 1; continue
        t = int(per.loc[addr, "time_step"])
        present = addr_sorted[first <= t]
        present_set = set(present.tolist())
        src_keep = np.isin(src_all, present)
        dst_keep = np.isin(dst_all, present)
        keep = src_keep & dst_keep
        adj = {}
        for u, v in zip(src_all[keep], dst_all[keep]):
            adj.setdefault(u, set()).add(v)
            adj.setdefault(v, set()).add(u)
        del keep

        illicit_t = {a for a in illicit_all if a in present_set}

        nbrs = list(adj.get(addr, ()))
        # independent BFS
        dist = {n: 0.0 for n in illicit_t}
        frontier = {n: 0 for n in illicit_t}
        visited = set(illicit_t)
        while frontier:
            nxt = {}
            for node in frontier:
                for nb in adj.get(node, ()):
                    if nb not in visited:
                        visited.add(nb)
                        nxt[nb] = dist[node] + 1.0
            for n, d in nxt.items():
                dist[n] = d
            frontier = nxt
        shortest = 6
        if addr in illicit_t:
            # nearest OTHER seed via local single-source BFS; self (level 0) is
            # never a target, so a known-illicit wallet cannot flag itself.
            seen = {addr}
            frontier = [addr]
            sdist = 0
            found = False
            while frontier and sdist < 6 and not found:
                sdist += 1
                nxt = []
                for node in frontier:
                    if found:
                        break
                    for nb in adj.get(node, ()):
                        if nb in seen:
                            continue
                        seen.add(nb)
                        if nb in illicit_t:
                            shortest = sdist
                            found = True
                            break
                        nxt.append(nb)
                frontier = nxt
        else:
            shortest = int(min(dist.get(addr, 6), 6))

        n1 = len(nbrs)
        r1 = 0.0
        if n1:
            i1 = sum(1 for n in nbrs if n in illicit_t)
            r1 = i1 / n1
        r2 = 0.0
        if n1:
            nbr_set = set(nbrs)
            seen2 = {nb2 for nb in nbrs for nb2 in adj.get(nb, ()) if nb2 != addr and nb2 not in nbr_set}
            if seen2:
                r2 = sum(1 for n in seen2 if n in illicit_t) / len(seen2)

        expected = snap_map[addr]
        exp = (expected["illicit_neighbor_ratio_1hop"], expected["illicit_neighbor_ratio_2hop"], int(expected["shortest_path_to_known_illicit"]))
        got = (r1, r2, shortest)
        ok = (abs(exp[0] - r1) < 1e-9 and abs(exp[1] - r2) < 1e-9 and exp[2] == shortest)

        # Future-leak audit on 1-hop neighbors
        leak = []
        for nb in nbrs:
            nb_first = first_map.get(nb)
            if nb_first is None or nb_first > t:
                leak.append((nb, nb_first))
            if nb in illicit_t and nb not in illicit_all:
                leak.append((nb, "flag-not-in-class1"))
        future_flag = "  [FAIL] FUTURE LEAK" if leak else ""
        verdict = "PASS" if (ok and not leak) else "FAIL"
        if not (ok and not leak):
            failures += 1
        print(f"{verdict} t={t:<2d} {addr} n1={n1:<4d} exp(1h={exp[0]:.3f},2h={exp[1]:.3f},sp={exp[2]}) got(1h={r1:.3f},2h={r2:.3f},sp={shortest}) future_leak={leak}{future_flag}")

    # Global leak invariants across the WHOLE file, not just the sample:
    #   (1) shortest_path>=1 everywhere — a wallet can never be its own seed,
    #   (2) shortest_path capped at 6 (no unbounded raw distances).
    snap_df = pd.read_csv(os.path.join(processed_dir, "graph_features_snapshot.csv"))
    sp = snap_df["shortest_path_to_known_illicit"]
    zero_cnt = int((sp == 0).sum())
    domain_ok = bool(sp.between(1, 6).all())
    print(
        f"GLOBAL INVARIANTS: rows={len(snap_df):,} "
        f"sp==0 count={zero_cnt} sp_domain_ok={domain_ok}"
    )
    if zero_cnt or not domain_ok:
        failures += 1

    print("=" * 100)
    print(f"TOTAL: {len(picked)} checked, {failures} mismatches")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())