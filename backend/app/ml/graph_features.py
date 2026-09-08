"""
app/ml/graph_features.py — Compute engineered graph topology features.

Extracts illicit neighbor ratios and shortest path distances from AddrAddr_edgelist.csv.
These features are used in addition to (not instead of) the tabular feature schema.

Uses NetworkX for efficient graph algorithms.
"""
import logging
import os

import numpy as np
import pandas as pd
import networkx as nx

logger = logging.getLogger(__name__)


def _get_graph_cache_path(data_dir: str, time_step_threshold: int | None) -> str:
    label = "full" if time_step_threshold is None else f"train_period_{time_step_threshold}"
    return os.path.join(
        data_dir,
        f"graph_features_{label}.csv",
    )


def load_training_period_graph(
    data_dir: str,
    time_step_threshold: int | None = 29,
) -> tuple[dict[str, int], nx.Graph, pd.DataFrame]:
    """
    Load the wallet graph and optionally filter to training-period edges.

    Args:
        data_dir: Path to ellipticpp data directory
        time_step_threshold: Max time step to include. None means use ALL time steps
            (full graph). This is required for fair offline evaluation because test-set
            wallets only appear in later time steps and would otherwise get zeroed-out
            graph features, creating a train/test distribution shift.

    Returns:
        - address_to_idx: mapping from address string to node index
        - G: NetworkX graph with (optionally filtered) edges
        - labels_df: DataFrame with address, label (1=illicit, 0=licit)
    """
    # Load wallet classes (labels)
    classes_path = os.path.join(data_dir, "wallets_classes.csv")
    classes_df = pd.read_csv(classes_path)

    # Load wallet features to get time_step
    features_path = os.path.join(data_dir, "wallets_features.csv")
    features_df = pd.read_csv(features_path)

    # Merge labels and features
    merged = features_df.merge(
        classes_df[["address", "class"]],
        on="address",
        how="inner",
    )

    # Keep only labeled nodes
    merged = merged[merged["class"].isin([1, 2])].copy()
    merged["label"] = (merged["class"] == 1).astype(int)  # 1=illicit, 0=licit

    # Optionally filter to training period
    merged["Time step"] = pd.to_numeric(merged["Time step"], errors="coerce")
    if time_step_threshold is not None:
        nodes = merged[merged["Time step"] <= time_step_threshold].copy()
        logger.info(f"Loaded {len(nodes)} training-period nodes from {time_step_threshold} time steps")
    else:
        nodes = merged.copy()
        logger.info(f"Loaded {len(nodes)} nodes from ALL time steps (full graph)")

    # Build address -> index mapping
    address_list = nodes["address"].astype(str).unique().tolist()
    address_to_idx = {addr: idx for idx, addr in enumerate(address_list)}

    # Load edge list
    edge_path = os.path.join(data_dir, "AddrAddr_edgelist.csv")
    edges_df = pd.read_csv(edge_path, header=None, names=["src", "dst"])

    # Filter edges to nodes in scope
    edges_df["src"] = edges_df["src"].astype(str)
    edges_df["dst"] = edges_df["dst"].astype(str)
    edges_in_scope = edges_df[
        (edges_df["src"].isin(address_to_idx)) & (edges_df["dst"].isin(address_to_idx))
    ].copy()

    logger.info(f"Loaded {len(edges_in_scope)} edges in scope subgraph")

    # Build NetworkX graph
    G = nx.Graph()
    G.add_nodes_from(range(len(address_to_idx)))

    for src_addr, dst_addr in edges_in_scope.values:
        src_idx = address_to_idx[src_addr]
        dst_idx = address_to_idx[dst_addr]
        G.add_edge(src_idx, dst_idx)

    logger.info(f"NetworkX graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    # Prepare labels dataframe
    labels_df = nodes[["address", "label"]].drop_duplicates(subset=["address"]).copy()
    labels_df["address"] = labels_df["address"].astype(str)

    return address_to_idx, G, labels_df


def compute_graph_features(
    data_dir: str,
    time_step_threshold: int | None = 29,
) -> pd.DataFrame:
    """
    Compute engineered graph features for all nodes using NetworkX.
    Uses efficient graph algorithms for k-hop and shortest path computation.

    Args:
        data_dir: Path to ellipticpp data directory
        time_step_threshold: Max time step to include in the graph. None means the
            FULL graph (all time steps), which is required for fair evaluation since
            test-set wallets only appear in later time steps.

    Returns:
        DataFrame with columns: address, illicit_neighbor_ratio_1hop, 
                                illicit_neighbor_ratio_2hop, shortest_path_to_known_illicit
    """
    cache_path = _get_graph_cache_path(data_dir, time_step_threshold)
    if os.path.exists(cache_path):
        logger.info(f"Loading cached graph features from {cache_path}")
        return pd.read_csv(cache_path)

    address_to_idx, G, labels_df = load_training_period_graph(data_dir, time_step_threshold)
    idx_to_address = {idx: addr for addr, idx in address_to_idx.items()}
    n_nodes = len(address_to_idx)

    # Build set of illicit node indices
    illicit_set = {
        address_to_idx[addr]
        for addr in labels_df[labels_df["label"] == 1]["address"].values
    }

    logger.info(f"Illicit nodes in graph: {len(illicit_set)}")

    # Efficient multi-source BFS from ALL illicit nodes in a single pass (O(V+E)).
    # This yields the exact same "distance to the NEAREST illicit node" as the
    # previous per-illicit-node BFS loop, but is drastically faster on the full graph.
    logger.info("Precomputing distance-to-illicit via multi-source BFS...")
    distance_to_illicit = {node: 0.0 for node in illicit_set}
    frontier = list(illicit_set)
    distance = 0
    visited = set(illicit_set)
    while frontier:
        next_frontier = []
        for node in frontier:
            for nb in G.neighbors(node):
                if nb not in visited:
                    visited.add(nb)
                    next_frontier.append(nb)
                    distance_to_illicit[nb] = float(distance + 1)
        frontier = next_frontier
        distance += 1
    logger.info(f"Reachable-from-illicit nodes: {len(distance_to_illicit)}")

    # Build neighbor maps for fast ratio computation.
    # For each node, precompute its 1-hop neighbors and counts of illicit neighbors.
    gall = G.adj

    # Only report features for LABELED nodes (licit/illicit). The full graph is still
    # used for BFS connectivity and neighbour lookups, but we don't need to emit rows
    # for the ~557K unlabeled nodes, which keeps the per-node loop tractable.
    labeled_indices = [
        address_to_idx[addr]
        for addr in labels_df["address"].values
    ]
    logger.info(f"Computing features for {len(labeled_indices)} labeled nodes")
    results = []
    batch = []
    for node_idx in labeled_indices:
        address = idx_to_address[node_idx]
        neighbors_1hop = list(gall[node_idx].keys())
        n1 = len(neighbors_1hop)
        ratio_1hop = 0.0
        ratio_2hop = 0.0

        if n1:
            illicit_1hop = sum(1 for n in neighbors_1hop if n in illicit_set)
            ratio_1hop = illicit_1hop / n1

            # 2-hop neighbors (exclude 1-hop and source)
            seen2 = set()
            for neighbor in neighbors_1hop:
                for second_neighbor in gall[neighbor].keys():
                    if second_neighbor != node_idx and second_neighbor not in neighbors_1hop:
                        seen2.add(second_neighbor)
            if seen2:
                illicit_2hop = sum(1 for n in seen2 if n in illicit_set)
                ratio_2hop = illicit_2hop / len(seen2)

        # Shortest path to illicit (capped at 6)
        if node_idx in illicit_set:
            shortest_path = 0
        else:
            shortest_path = int(min(distance_to_illicit.get(node_idx, 6), 6))

        batch.append({
            "address": address,
            "illicit_neighbor_ratio_1hop": float(ratio_1hop),
            "illicit_neighbor_ratio_2hop": float(ratio_2hop),
            "shortest_path_to_known_illicit": shortest_path,
        })
        if (len(batch) % 20000) == 0:
            logger.info(f"Processed {len(batch)} nodes...")
            results.extend(batch)
            batch = []

    results.extend(batch)
    result_df = pd.DataFrame(results)
    logger.info(f"Computed graph features for {len(result_df)} nodes")
    result_df.to_csv(cache_path, index=False)
    logger.info(f"Saved cached graph features to {cache_path}")

    return result_df


if __name__ == "__main__":
    # For standalone testing
    import sys
    
    logging.basicConfig(level=logging.INFO)
    
    if len(sys.argv) > 1:
        data_dir = sys.argv[1]
    else:
        data_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "ellipticpp")
        )
    
    print(f"Loading graph features from {data_dir}")
    graph_features = compute_graph_features(data_dir)
    print(graph_features.head(10))
    print(f"\nShape: {graph_features.shape}")
    print(f"Illicit 1-hop ratio stats:\n{graph_features['illicit_neighbor_ratio_1hop'].describe()}")
    print(f"Illicit 2-hop ratio stats:\n{graph_features['illicit_neighbor_ratio_2hop'].describe()}")
    print(f"Shortest path stats:\n{graph_features['shortest_path_to_known_illicit'].describe()}")
