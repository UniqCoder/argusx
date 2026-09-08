"""
app/ml/snapshot_graph_features.py — Leak-safe (point-in-time) graph features.

Same three features as graph_features.py
(illicit_neighbor_ratio_1hop / _2hop / shortest_path_to_known_illicit) but
computed from a TIME-ORDERED snapshot of the Elliptic++ wallet graph, so no
future information leaks into a wallet's features:

  - A wallet with era ``t`` gets its features computed on ``G_t`` = the
    induced subgraph of addresses that are already KNOWN by step ``t``
    (first appearance ≤ t) and the AddrAddr edges among them.
  - KNOWN ILLICIT SEEDS are restricted to TRAIN-SPLIT labeled illicit
    wallets only (class==1 AND the address is a member of train.csv, i.e.
    its last appearance is within the training window ≤ 29). Val/test gold
    labels never enter any feature — a test-period wallet thus cannot see
    its own or any future gold label through the graph columns. This closes
    the leak that previously let BTC test AUC-PR reach a perfect 1.0000 by
    re-encoding the evaluation target.
  - A queried wallet is NEVER its own seed:
    ``shortest_path_to_known_illicit`` = distance to the nearest OTHER
    train-known-illicit wallet (capped at 6). A wallet that IS itself a
    known-TRAIN-illicit seed therefore gets shortest=1..6 (distance to a
    distinct neighbor seed), never 0 for itself.

Documented limitation (inherited from the dataset): AddrAddr_edgelist.csv has
no per-edge timestamp, so an edge is treated as "known at t" iff both endpoints
are known by t. This is the same proxy the project's existing graph code uses.
"""
from __future__ import annotations

import csv
import logging
import os

import numpy as np
import pandas as pd
from scipy.sparse import coo_matrix

logger = logging.getLogger(__name__)

GRAPH_FEATURE_COLS = [
    "illicit_neighbor_ratio_1hop",
    "illicit_neighbor_ratio_2hop",
    "shortest_path_to_known_illicit",
]

SHORTEST_PATH_CAP = 6

# Last Timestep of the TRAIN split (wallets whose last appearance <= 29 belong
# to train.csv; see data/processed/split). Used only as a heuristic fallback —
# the exact TRAIN-split seed set comes from train.csv when provided.
TRAIN_WINDOW_LAST_STEP = 29

# Explicitly-defined CSV dtype/editors so the module stays honest about case.
ADDRESS_LOWER = "address"
TIME_STEP_COL = "Time step"


def _load_train_addresses(train_split_path: str | None) -> set[str] | None:
    """Load the address set of the TRAIN split (lowercased), or None if absent.

    The seed restriction lives and dies on this set: a known-illicit seed is
    only ever an address whose label was visible during training.
    """
    if train_split_path is None:
        return None
    tr = pd.read_csv(train_split_path, usecols=[ADDRESS_LOWER])
    return set(tr[ADDRESS_LOWER].astype(str).str.lower())


def _load_data(data_dir: str, train_split_path: str | None = None) -> dict:
    """Load the minimal frames needed for snapshot graph features (lowercased)."""
    feats = pd.read_csv(
        os.path.join(data_dir, "wallets_features.csv"),
        usecols=[ADDRESS_LOWER, TIME_STEP_COL],
    )
    feats[ADDRESS_LOWER] = feats[ADDRESS_LOWER].astype(str).str.lower()
    feats[TIME_STEP_COL] = pd.to_numeric(feats[TIME_STEP_COL], errors="coerce")

    classes = pd.read_csv(os.path.join(data_dir, "wallets_classes.csv"))
    classes[ADDRESS_LOWER] = classes[ADDRESS_LOWER].astype(str).str.lower()
    classes = classes.drop_duplicates(subset=[ADDRESS_LOWER]).copy()

    edge = pd.read_csv(os.path.join(data_dir, "AddrAddr_edgelist.csv"))
    edge.columns = ["src", "dst"]
    edge["src"] = edge["src"].astype(str).str.lower()
    edge["dst"] = edge["dst"].astype(str).str.lower()
    # Self-loops are silently dropped: the live serving queries never count a
    # wallet as its own neighbor, so training parity requires the same.
    edge = edge[edge["src"] != edge["dst"]].copy()

    raw = {"feats": feats, "classes": classes, "edge": edge}
    raw["train_set"] = _load_train_addresses(train_split_path)
    return raw


def _build_illicit_seeds(classes: pd.DataFrame, per_addr: pd.DataFrame,
                         train_set: set[str] | None) -> dict[str, int]:
    """Known-illicit seed addresses -> first appearance, RESTRICTED to training.

    A seed is (class==1 AND address in the TRAIN split). When train.csv is not
    available, falls back to the first-appearance<=29 heuristic with a warning
    (never silently broader than the window a model could know at t).
    """
    class1 = set(classes.loc[classes["class"] == 1, ADDRESS_LOWER].astype(str))
    if train_set is not None:
        seeds = class1 & train_set
    else:
        first_map = per_addr["first"].to_dict()
        seeds = {a for a in class1 if int(first_map[a]) <= TRAIN_WINDOW_LAST_STEP}
        logger.warning(
            "No train.csv provided — restricted seeds heuristically to "
            "class==1 addresses with first appearance <= %d; prefer passing "
            "train_split_path for the exact TRAIN-split seed set.",
            TRAIN_WINDOW_LAST_STEP,
        )
    return {a: int(per_addr.loc[a, "first"]) for a in seeds if a in per_addr.index}


def _expand_neighbors(indptr: np.ndarray, indices: np.ndarray, frontier: np.ndarray) -> np.ndarray:
    """All (raw, possibly duplicated) neighbors of every node in ``frontier``."""
    if frontier.size == 0:
        return np.empty(0, dtype=np.int64)
    starts = indptr[frontier]
    lens = indptr[frontier + 1] - starts
    total = int(lens.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64)
    base = starts.repeat(lens)
    ranks = np.arange(total, dtype=np.int64) - np.repeat(lens.cumsum() - lens, lens)
    return indices[base + ranks]


def _multi_source_bfs(indptr: np.ndarray, indices: np.ndarray, seeds: np.ndarray,
                      n_nodes: int, cap: int) -> np.ndarray:
    """Multi-source BFS over a CSR graph, early-stopped at depth ``cap``.

    ``dist[i]`` = unvisited/far -> max-int32 sentinel, else shortest hop distance
    from the nearest seed (capped: anything beyond ``cap`` stays a sentinel and is
    read back as ``cap`` by callers).
    """
    dist = np.full(n_nodes, np.iinfo(np.int32).max, dtype=np.int32)
    visited = np.zeros(n_nodes, dtype=bool)
    dist[seeds] = 0
    visited[seeds] = True
    frontier = seeds
    d = 0
    while frontier.size and d < cap:
        d += 1
        nbrs = _expand_neighbors(indptr, indices, frontier)
        if nbrs.size == 0:
            break
        unvis = nbrs[~visited[nbrs]]
        if unvis.size == 0:
            break
        dist[unvis] = d
        visited[unvis] = True
        frontier = np.unique(unvis)
    return dist


def _nearest_other_illicit_id(indptr: np.ndarray, indices: np.ndarray,
                              addr_i: int, illicit_flag: np.ndarray) -> int:
    """Distance from node ``addr_i`` to the nearest OTHER illicit seed.

    Single-source BFS; ``addr_i`` itself (level 0) is never a target, so a
    known-train-illicit wallet never flags itself (shortest=0).
    """
    seen = {addr_i}
    frontier = [addr_i]
    d = 0
    while frontier and d < SHORTEST_PATH_CAP:
        d += 1
        nxt: list[int] = []
        for node in frontier:
            for nb in indices[indptr[node]:indptr[node + 1]]:
                if nb in seen:
                    continue
                seen.add(nb)
                if illicit_flag[nb]:
                    return d
                nxt.append(nb)
        frontier = nxt
    return SHORTEST_PATH_CAP


def compute_snapshot_graph_features(
    data_dir: str,
    out_path: str,
    train_split_path: str | None = None,
    log_every: int = 20000,
    max_steps: int | None = None,
) -> pd.DataFrame:
    """
    Compute point-in-time graph features for every labeled Elliptic++ wallet.

    Memory-lean build: addresses are relabelled to contiguous int64 ids once and
    per-timestep adjacency is a compact scipy CSR matrix (instead of a
    Python dict-of-sets over 2.8M edges) so the whole 822k-wallet build runs in
    ~1.2GB and streams each timestep's rows to the CSV as it goes.

    Returns a DataFrame with columns:
        address, time_step, illicit_neighbor_ratio_1hop,
        illicit_neighbor_ratio_2hop, shortest_path_to_known_illicit
    where ``time_step`` is the LAST timestep row for that address (the row the
    training splits actually use) and features were computed on the snapshot
    G_{time_step} (no future data).
    """
    raw = _load_data(data_dir, train_split_path)
    feats, classes, edge = raw["feats"], raw["classes"], raw["edge"]

    per_addr = feats.groupby(ADDRESS_LOWER)[TIME_STEP_COL].agg(["min", "max"]).copy()
    per_addr.columns = ["first", "time_step"]

    # Known-illicit seeds restricted to the TRAIN split (class==1 AND train.csv).
    # Val/test gold labels are never seeds, closing the label-re-encoding leak
    # that caused BTC test AUC-PR==1.0000 on the previous graph-fix swap.
    seed_by_first = _build_illicit_seeds(classes, per_addr, raw["train_set"])

    # ── address -> contiguous int64 id ───────────────────────────────────────
    addr_sorted = np.array(sorted(per_addr.index), dtype="<U40")
    addr_to_id = {a: i for i, a in enumerate(addr_sorted)}

    edge = edge[edge["src"].isin(addr_to_id) & edge["dst"].isin(addr_to_id)].copy()
    src_id = edge["src"].map(addr_to_id).to_numpy(dtype=np.int64)
    dst_id = edge["dst"].map(addr_to_id).to_numpy(dtype=np.int64)
    logger.info("Loaded %d AddrAddr edges (%d wallets)", src_id.size, len(addr_sorted))

    first_arr = per_addr["first"].to_numpy(dtype=np.float64)          # aligned to addr_sorted
    time_step_arr = per_addr["time_step"].to_numpy(dtype=np.int64)    # aligned to addr_sorted
    n_nodes = len(addr_sorted)

    seed_id_first = {addr_to_id[a]: int(f0) for a, f0 in seed_by_first.items()}
    illicit_all_flag = np.zeros(n_nodes, dtype=bool)
    if seed_id_first:
        illicit_all_flag[list(seed_id_first)] = True

    unique_steps = sorted(int(x) for x in per_addr["time_step"].dropna().unique())
    if max_steps is not None:
        unique_steps = unique_steps[:max_steps]

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    rows: list[tuple] = []
    total_rows = 0
    with open(out_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([ADDRESS_LOWER, "time_step", *GRAPH_FEATURE_COLS])

        for t in unique_steps:
            present = first_arr <= t
            keep = present[src_id] & present[dst_id]
            ss = src_id[keep]
            dd = dst_id[keep]
            # Undirected adjacency for step t (coo -> csr, deduped; +T makes it
            # symmetric). Membership is what matters, not edge multiplicity.
            At = coo_matrix((np.ones(ss.size, dtype=np.bool_), (ss, dd)), shape=(n_nodes, n_nodes))
            At = At.tocsr() + At.T.tocsr()
            indptr = At.indptr
            indices = At.indices
            del At, ss, dd, keep

            # Seeds known by step t (train-split illicit with first appearance <= t).
            seeds_t = np.array(
                [sid for sid, f0 in seed_id_first.items() if f0 <= t], dtype=np.int64
            )
            illicit_flag = np.zeros(n_nodes, dtype=bool)
            if seeds_t.size:
                illicit_flag[seeds_t] = True

            if seeds_t.size:
                dist = _multi_source_bfs(indptr, indices, seeds_t, n_nodes, SHORTEST_PATH_CAP)
            else:
                dist = np.full(n_nodes, np.iinfo(np.int32).max, dtype=np.int32)

            # Wallets whose own last timestep == t.
            step_ids = np.nonzero(time_step_arr == t)[0]
            step_rows: list[tuple] = []
            for addr_i in step_ids:
                n0, n1 = indptr[addr_i], indptr[addr_i + 1]
                nbrs = indices[n0:n1]
                ratio_1hop = 0.0
                ratio_2hop = 0.0
                if n1 > n0:
                    illicit_1hop = int(illicit_flag[nbrs].sum())
                    ratio_1hop = illicit_1hop / (n1 - n0)
                    nbr_set = set(nbrs.tolist())
                    seen2: set[int] = set()
                    for nb in nbrs:
                        for nb2 in indices[indptr[nb]:indptr[nb + 1]]:
                            if nb2 != addr_i and nb2 not in nbr_set:
                                seen2.add(nb2)
                    if seen2:
                        illicit_2hop = sum(1 for n in seen2 if illicit_flag[n])
                        ratio_2hop = illicit_2hop / len(seen2)

                if illicit_flag[addr_i]:
                    shortest = _nearest_other_illicit_id(indptr, indices, addr_i, illicit_flag)
                else:
                    sd = int(dist[addr_i])
                    shortest = SHORTEST_PATH_CAP if sd == np.iinfo(np.int32).max else sd

                step_rows.append((addr_sorted[addr_i], int(t), float(ratio_1hop), float(ratio_2hop), shortest))

            rows.extend(step_rows)
            total_rows += len(step_rows)
            writer.writerows(step_rows)
            del step_rows, step_ids, seeds_t, illicit_flag, dist, present

            if total_rows >= log_every and t % 5 == 0:
                logger.info("Snapshot progress: t=%d, rows so far=%d", t, total_rows)

    logger.info("Wrote %d snapshot graph feature rows to %s", total_rows, out_path)
    return pd.DataFrame(rows, columns=[ADDRESS_LOWER, "time_step", *GRAPH_FEATURE_COLS])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    import sys

    data_dir = sys.argv[1] if len(sys.argv) > 1 else "/app/data/raw/ellipticpp"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "/app/data/processed/graph_features_snapshot.csv"
    train_split_path = sys.argv[3] if len(sys.argv) > 3 else "/app/data/processed/train.csv"
    compute_snapshot_graph_features(data_dir, out_path, train_split_path)