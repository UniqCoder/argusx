"""Offline GraphSAGE benchmark for the wallet risk model.

This module intentionally keeps the live /risk endpoint untouched. It benchmarks an
offline GraphSAGE + XGBoost pipeline against the existing tabular-only XGBoost
baseline while preserving the same validation-slice threshold procedure.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn.functional as F
import xgboost as xgb
from sklearn.metrics import (
    auc,
    average_precision_score,
    confusion_matrix,
    precision_score,
    recall_score,
    roc_auc_score,
)
from torch_geometric.data import Data
from torch_geometric.nn import SAGEConv

from app.ml.features import FEATURE_COLUMNS, MISSING_INDICATOR_COLUMNS, assert_feature_schema
from app.ml.train import DATASET_TO_CANONICAL_RENAME, canonicalize_training_features, get_data_dir, get_processed_dir, select_best_threshold

logger = logging.getLogger(__name__)

GRAPH_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "raw", "ellipticpp"))


class GraphSAGERiskModel(torch.nn.Module):
    """2-layer GraphSAGE encoder with a binary classification head."""

    def __init__(self, in_channels: int, hidden_channels: int = 32, embedding_dim: int = 16):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, hidden_channels)
        self.embedding = torch.nn.Linear(hidden_channels, embedding_dim)
        self.classifier = torch.nn.Linear(embedding_dim, 2)

    def encode(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = self.conv2(x, edge_index)
        x = F.relu(x)
        return self.embedding(x)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        embedding = self.encode(x, edge_index)
        return self.classifier(embedding)


def load_labeled_wallet_graph(data_dir: str | None = None) -> tuple[pd.DataFrame, Data, dict[str, np.ndarray], torch.Tensor]:
    """Load the real wallet graph and keep the temporal split boundaries explicit."""
    data_dir = data_dir or get_data_dir()
    feature_path = os.path.join(data_dir, "wallets_features.csv")
    class_path = os.path.join(data_dir, "wallets_classes.csv")
    edge_path = os.path.join(data_dir, "AddrAddr_edgelist.csv")

    wallet_features = pd.read_csv(feature_path)
    wallet_classes = pd.read_csv(class_path)
    edge_list = pd.read_csv(edge_path, header=0, names=["src", "dst"])

    df = wallet_features.merge(wallet_classes[["address", "class"]], on="address", how="inner")
    df = df.drop_duplicates()  # remove exact-copy rows first
    df = df.drop_duplicates(subset=["address"], keep="last").copy()
    df = df[df["class"].isin([1, 2])].copy()
    df["label"] = (df["class"] == 1).astype(int)

    canonical = df.rename(columns=DATASET_TO_CANONICAL_RENAME)
    missing = [column for column in FEATURE_COLUMNS if column not in canonical.columns]
    if missing:
        canonical = canonical.assign(**{column: np.nan for column in missing})
    canonical = canonical[FEATURE_COLUMNS]
    canonical["address"] = df["address"].astype(str)
    canonical["time_step"] = pd.to_numeric(df["Time step"], errors="coerce")
    canonical["label"] = df["label"].astype(int)

    train_mask = canonical["time_step"].le(29).to_numpy(dtype=bool)
    val_mask = canonical["time_step"].between(30, 34).to_numpy(dtype=bool)
    test_mask = canonical["time_step"].ge(35).to_numpy(dtype=bool)

    node_to_index = {addr: idx for idx, addr in enumerate(canonical["address"].tolist())}
    edges: list[list[int]] = []
    for row in edge_list.itertuples(index=False):
        src, dst = str(row.src), str(row.dst)
        if src in node_to_index and dst in node_to_index:
            edges.append([node_to_index[src], node_to_index[dst]])
            edges.append([node_to_index[dst], node_to_index[src]])

    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous() if edges else torch.empty((2, 0), dtype=torch.long)
    train_edges = [
        [src, dst] for src, dst in zip(edge_index[0].tolist(), edge_index[1].tolist())
        if train_mask[src] and train_mask[dst]
    ]
    train_edge_index = torch.tensor(train_edges, dtype=torch.long).t().contiguous() if train_edges else torch.empty((2, 0), dtype=torch.long)

    x = torch.tensor(canonical[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32), dtype=torch.float32)
    y = torch.tensor(canonical["label"].to_numpy(dtype=np.int64), dtype=torch.long)
    split_masks = {
        "train": torch.tensor(train_mask),
        "val": torch.tensor(val_mask),
        "test": torch.tensor(test_mask),
    }

    graph = Data(x=x, edge_index=edge_index, y=y)
    graph.train_mask = split_masks["train"]
    graph.val_mask = split_masks["val"]
    graph.test_mask = split_masks["test"]

    return canonical, graph, split_masks, train_edge_index


def load_processed_wallet_graph(processed_dir: str | None = None) -> tuple[pd.DataFrame, Data, dict[str, np.ndarray], torch.Tensor]:
    """Load the graph node set from the preprocessed splits at data/processed/.

    Node set = the 265,354 BTC-labeled wallets (train+val+test), identical to the
    production 72-feature XGBoost model. Node features are the 72 canonical features
    with NaN filled as 0.0 (graph feature columns are NaN in the CSVs, matching the
    production fillna(0.0) path at train time). Split membership comes from the split
    files themselves (not time_step ranges) so masks match production exactly.

    Address normalization: the processed pipeline lowercases wallet addresses, while the
    raw AddrAddr_edgelist keeps base58 preserve-case. Edgelist endpoints are lowercased
    here to match (safe: no lowercase collisions in the labeled set).
    """
    processed_dir = processed_dir or get_processed_dir()
    splits = {name: pd.read_csv(os.path.join(processed_dir, f"{name}.csv")) for name in ("train", "val", "test")}
    btc_frames = []
    split_labels: list[str] = []
    for name, frame in splits.items():
        btc = frame[frame["chain"].astype(str) == "BTC"].copy()
        btc["split"] = name
        btc_frames.append(btc)
        split_labels.extend([name] * len(btc))
    canonical = pd.concat(btc_frames, ignore_index=True)
    canonical["address"] = canonical["address"].astype(str)

    feature_matrix = canonical[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32)
    labels = (canonical["label"] == 1).astype(int).to_numpy()
    split_arr = np.asarray(split_labels)

    mask_by_split = {name: split_arr == name for name in ("train", "val", "test")}

    node_to_index = {addr: idx for idx, addr in enumerate(canonical["address"].tolist())}
    edge_path = os.path.join(os.path.dirname(processed_dir), "raw", "ellipticpp", "AddrAddr_edgelist.csv")
    if not os.path.exists(edge_path):
        edge_path = os.path.join(processed_dir, "AddrAddr_edgelist.csv")
    edge_list = pd.read_csv(edge_path, header=0, names=["src", "dst"])
    edge_list["src"] = edge_list["src"].astype(str).str.lower()
    edge_list["dst"] = edge_list["dst"].astype(str).str.lower()

    edges: list[list[int]] = []
    for row in edge_list.itertuples(index=False):
        src, dst = row.src, row.dst
        if src in node_to_index and dst in node_to_index:
            edges.append([node_to_index[src], node_to_index[dst]])
            edges.append([node_to_index[dst], node_to_index[src]])

    edge_index = torch.tensor(edges, dtype=torch.long).t().contiguous() if edges else torch.empty((2, 0), dtype=torch.long)
    train_mask = mask_by_split["train"]
    train_edges = [
        [src, dst] for src, dst in zip(edge_index[0].tolist(), edge_index[1].tolist())
        if train_mask[src] and train_mask[dst]
    ]
    train_edge_index = torch.tensor(train_edges, dtype=torch.long).t().contiguous() if train_edges else torch.empty((2, 0), dtype=torch.long)

    x = torch.tensor(feature_matrix, dtype=torch.float32)
    y = torch.tensor(labels, dtype=torch.long)
    split_masks = {
        "train": torch.tensor(train_mask),
        "val": torch.tensor(mask_by_split["val"]),
        "test": torch.tensor(mask_by_split["test"]),
    }

    graph = Data(x=x, edge_index=edge_index, y=y)
    graph.train_mask = split_masks["train"]
    graph.val_mask = split_masks["val"]
    graph.test_mask = split_masks["test"]

    return canonical, graph, split_masks, train_edge_index


def train_graphsage(graph: Data, train_edge_index: torch.Tensor | None = None, epochs: int = 25, lr: float = 1e-3, weight_decay: float = 5e-4, seed: int = 42) -> GraphSAGERiskModel:
    """Train a 2-layer GraphSAGE classifier on train-period nodes and train-only edges."""
    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = GraphSAGERiskModel(in_channels=graph.x.size(1), hidden_channels=32, embedding_dim=16).to(device)
    graph = graph.to(device)
    train_edge_index = train_edge_index.to(device) if train_edge_index is not None else graph.edge_index
    train_mask = graph.train_mask
    optimizer = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    loss_fn = torch.nn.CrossEntropyLoss()

    for epoch in range(1, epochs + 1):
        model.train()
        optimizer.zero_grad()
        logits = model(graph.x, train_edge_index)
        loss = loss_fn(logits[train_mask], graph.y[train_mask])
        loss.backward()
        optimizer.step()

        if epoch % 5 == 0 or epoch == 1:
            with torch.no_grad():
                model.eval()
                preds = torch.argmax(model(graph.x, train_edge_index), dim=1)
                train_acc = (preds[train_mask] == graph.y[train_mask]).float().mean().item()
                logger.info("epoch=%s loss=%.4f train_acc=%.4f", epoch, loss.item(), train_acc)

    return model.to("cpu")


def extract_all_embeddings(model: GraphSAGERiskModel, graph: Data) -> np.ndarray:
    with torch.no_grad():
        model.eval()
        embeddings = model.encode(graph.x, graph.edge_index).cpu().numpy()
    return embeddings.astype(np.float32)


def compute_graph_embedding_metrics(
    graph: Data,
    embeddings: np.ndarray,
    feature_df: pd.DataFrame,
    threshold_candidates: list[float] | None = None,
    use_fair_hyperparameters: bool = True,
) -> dict[str, Any]:
    """Train XGBoost on tabular-only and tabular+embedding features using the same threshold scan.
    
    Args:
        use_fair_hyperparameters: If True, use identical hyperparameters to the production baseline
                                  (n_estimators=150, scale_pos_weight computed from training set).
                                  If False, use the original unfair comparison.
    """
    threshold_candidates = threshold_candidates or [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
    feature_df = feature_df.copy()
    feature_df["label"] = graph.y.cpu().numpy().astype(int)
    feature_df["split"] = "other"
    feature_df.loc[graph.train_mask.cpu().numpy(), "split"] = "train"
    feature_df.loc[graph.val_mask.cpu().numpy(), "split"] = "val"
    feature_df.loc[graph.test_mask.cpu().numpy(), "split"] = "test"

    all_features = feature_df[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32)
    y = feature_df["label"].to_numpy(dtype=int)

    train_idx = feature_df["split"].eq("train").to_numpy()
    val_idx = feature_df["split"].eq("val").to_numpy()
    test_idx = feature_df["split"].eq("test").to_numpy()

    baseline_X_train = all_features[train_idx]
    baseline_X_val = all_features[val_idx]
    baseline_X_test = all_features[test_idx]
    baseline_y_train = y[train_idx]
    baseline_y_val = y[val_idx]
    baseline_y_test = y[test_idx]

    emb_train = embeddings[train_idx]
    emb_val = embeddings[val_idx]
    emb_test = embeddings[test_idx]

    # Compute class-weight adjustment for imbalance
    scale_pos_weight = (len(baseline_y_train) - baseline_y_train.sum()) / max(1, baseline_y_train.sum())
    
    # Select XGBoost hyperparameters based on fairness requirement
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
    embed_val_prob = xgb_embed.predict_proba(xgb_embed_X_val)[:, 1]
    embed_thresh, embed_summary = select_best_threshold(pd.Series(baseline_y_val), embed_val_prob, threshold_candidates)

    def eval_metrics(labels: np.ndarray, probs: np.ndarray, threshold: float) -> dict[str, float | int]:
        preds = (probs >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(labels, preds, labels=[0, 1]).ravel()
        precision = precision_score(labels, preds, zero_division=0)
        recall = recall_score(labels, preds, zero_division=0)
        fpr = fp / max(1, fp + tn)
        return {
            "threshold": float(threshold),
            "precision": float(precision),
            "recall": float(recall),
            "fpr": float(fpr),
            "auc_pr": float(average_precision_score(labels, probs)),
            "auc_roc": float(roc_auc_score(labels, probs)),
            "tp": int(tp),
            "fp": int(fp),
            "tn": int(tn),
            "fn": int(fn),
        }

    baseline_test_metrics = eval_metrics(baseline_y_test, xgb_baseline.predict_proba(baseline_X_test)[:, 1], baseline_thresh)
    embed_test_metrics = eval_metrics(baseline_y_test, xgb_embed.predict_proba(xgb_embed_X_test)[:, 1], embed_thresh)

    return {
        "baseline": {
            "validation_threshold": baseline_thresh,
            "validation": baseline_summary,
            "test": baseline_test_metrics,
        },
        "graphsage_embedding": {
            "validation_threshold": embed_thresh,
            "validation": embed_summary,
            "test": embed_test_metrics,
        },
    }


def compute_processed_embedding_metrics(
    graph: Data,
    embeddings: np.ndarray,
    btc_node_frame: pd.DataFrame,
    processed_dir: str | None = None,
    threshold_candidates: list[float] | None = None,
) -> dict[str, Any]:
    """Train 72-feature baseline and 88-feature GraphSAGE arms on the SAME data/processed splits.

    Mirrors train_combined_model: per-chain sample weights from the processed train split,
    combined-val threshold scan (max FPR 2%), combined-test confusion matrix, and BTC test
    metrics. ETH rows have no wallet-graph node, so they receive zero-vector embeddings.
    """
    import warnings
    warnings.filterwarnings("ignore", message="Predicted probabilities.*", category=UserWarning)

    threshold_candidates = threshold_candidates or [0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.88, 0.90, 0.92, 0.95]
    processed_dir = processed_dir or get_processed_dir()
    train_df = pd.read_csv(os.path.join(processed_dir, "train.csv"))
    val_df = pd.read_csv(os.path.join(processed_dir, "val.csv"))
    test_df = pd.read_csv(os.path.join(processed_dir, "test.csv"))

    emby_by_address = {addr: emb for addr, emb in zip(btc_node_frame["address"].astype(str).tolist(), embeddings)}
    embed_dim = embeddings.shape[1]

    def _augment(frame: pd.DataFrame) -> pd.DataFrame:
        aug_emb = np.zeros((len(frame), embed_dim), dtype=np.float32)
        for idx, addr in enumerate(frame["address"].astype(str).to_numpy()):
            if addr in emby_by_address:
                aug_emb[idx] = emby_by_address[addr]
        return pd.DataFrame(
            {f"gsage_{dim}": aug_emb[:, dim] for dim in range(embed_dim)},
            index=frame.index,
        )

    train_aug = _augment(train_df)
    val_aug = _augment(val_df)
    test_aug = _augment(test_df)

    xgb_kwargs = {
        "n_estimators": 150,
        "max_depth": 5,
        "learning_rate": 0.06,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "eval_metric": "logloss",
        "random_state": 42,
        "tree_method": "hist",
    }
    sample_weights = train_df["sample_weight"].to_numpy()

    def _fit_predict(aug_train: pd.DataFrame, aug_val: pd.DataFrame, aug_test: pd.DataFrame) -> tuple[xgb.XGBClassifier, float, dict, dict]:
        clf = xgb.XGBClassifier(**xgb_kwargs)
        clf.fit(aug_train[FEATURE_COLUMNS].fillna(0.0), train_df["label"], sample_weight=sample_weights)
        val_prob = clf.predict_proba(aug_val[FEATURE_COLUMNS].fillna(0.0))[:, 1]
        threshold, summary = select_best_threshold(val_df["label"], val_prob, threshold_candidates)
        test_prob = clf.predict_proba(aug_test[FEATURE_COLUMNS].fillna(0.0))[:, 1]
        return clf, threshold, summary, test_prob

    baseline_clf, baseline_thresh, baseline_val_summary, baseline_test_prob = _fit_predict(train_df, val_df, test_df)

    def _eval_metrics(labels: pd.Series, probs: np.ndarray, threshold: float) -> dict[str, float | int]:
        preds = (probs >= threshold).astype(int)
        tn, fp, fn, tp = confusion_matrix(labels, preds).ravel()
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        fpr = fp / max(1, fp + tn)
        return {
            "rows": int(len(labels)),
            "threshold": float(threshold),
            "precision": float(precision),
            "recall": float(recall),
            "fpr": float(fpr),
            "auc_pr": float(average_precision_score(labels, probs)),
            "auc_roc": float(roc_auc_score(labels, probs)),
            "tp": int(tp),
            "fp": int(fp),
            "tn": int(tn),
            "fn": int(fn),
        }

    baseline_combined = _eval_metrics(test_df["label"], baseline_test_prob, baseline_thresh)
    baseline_btc_mask = test_df["chain"].astype(str) == "BTC"
    baseline_btc = _eval_metrics(
        test_df.loc[baseline_btc_mask, "label"],
        baseline_test_prob[baseline_btc_mask.to_numpy()],
        baseline_thresh,
    )

    gsage_cols = [f"gsage_{dim}" for dim in range(embed_dim)]
    embed_train = np.hstack([train_df[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32), train_aug[gsage_cols].to_numpy(dtype=np.float32)])
    embed_val = np.hstack([val_df[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32), val_aug[gsage_cols].to_numpy(dtype=np.float32)])
    embed_test = np.hstack([test_df[FEATURE_COLUMNS].fillna(0.0).to_numpy(dtype=np.float32), test_aug[gsage_cols].to_numpy(dtype=np.float32)])

    embed_clf = xgb.XGBClassifier(**xgb_kwargs)
    embed_clf.fit(embed_train, train_df["label"], sample_weight=sample_weights)
    embed_val_prob = embed_clf.predict_proba(embed_val)[:, 1]
    embed_thresh, embed_val_summary = select_best_threshold(val_df["label"], embed_val_prob, threshold_candidates)
    embed_test_prob = embed_clf.predict_proba(embed_test)[:, 1]

    embed_combined = _eval_metrics(test_df["label"], embed_test_prob, embed_thresh)
    embed_btc = _eval_metrics(
        test_df.loc[baseline_btc_mask, "label"],
        embed_test_prob[baseline_btc_mask.to_numpy()],
        embed_thresh,
    )

    return {
        "model": "retrained_on_processed_splits",
        "feature_counts": {"baseline": len(FEATURE_COLUMNS), "graphsage_embedding": len(FEATURE_COLUMNS) + embed_dim},
        "split_rows": {
            "train": int(len(train_df)),
            "val": int(len(val_df)),
            "test": int(len(test_df)),
            "graph_nodes_btc": int(len(btc_node_frame)),
        },
        "baseline": {
            "validation_threshold": baseline_thresh,
            "validation": baseline_val_summary,
            "combined_test": baseline_combined,
            "btc_test": baseline_btc,
        },
        "graphsage_embedding": {
            "validation_threshold": embed_thresh,
            "validation": embed_val_summary,
            "combined_test": embed_combined,
            "btc_test": embed_btc,
        },
    }


def run_retrained_graphsage_benchmark(data_dir: str | None = None, processed_dir: str | None = None) -> dict[str, Any]:
    """Retrain GraphSAGE on the data/processed/ splits and return the 72f-vs-88f report."""
    processed_dir = processed_dir or get_processed_dir()
    btc_node_frame, graph, _, train_edge_index = load_processed_wallet_graph(processed_dir)
    model = train_graphsage(graph, train_edge_index=train_edge_index, seed=42)
    embeddings = extract_all_embeddings(model, graph)
    report = compute_processed_embedding_metrics(graph, embeddings, btc_node_frame, processed_dir)
    report["graph_nodes"] = {
        "btc_labeled_nodes": int(len(btc_node_frame)),
        "train_nodes": int(graph.train_mask.sum()),
        "val_nodes": int(graph.val_mask.sum()),
        "test_nodes": int(graph.test_mask.sum()),
        "edges": int(graph.edge_index.size(1) // 2),
        "train_edges": int(train_edge_index.size(1) // 2),
    }
    report["processed_dir"] = processed_dir
    return report


def compute_graph_context_summary(address: str) -> dict[str, Any]:
    """Return a lightweight graph-neighborhood summary for a live address.

    If Neo4j is unavailable or a neighborhood is sparse, the mode is marked as
    fallback so the live-serving path can degrade gracefully without forcing a
    low-quality embedding into the model.
    """
    summary = {
        "address": address,
        "neighbor_count": 0,
        "is_sparse": True,
        "mode": "fallback",
        "details": [],
    }

    try:
        from app.graph.neo4j_client import run_query

        query = """
        MATCH (a:Wallet {address: $address})
        OPTIONAL MATCH (a)-[:SENT|RECEIVED_BY|BELONGS_TO*1..2]-(n:Wallet)
        WITH a, collect(DISTINCT n.address) AS neighbors
        RETURN size(neighbors) AS neighbor_count, neighbors
        """

        async def _fetch() -> list[dict[str, Any]]:
            return await run_query(query, {"address": address})

        rows = asyncio.run(_fetch())
        if rows:
            row = rows[0]
            neighbor_count = int(row.get("neighbor_count", 0) or 0)
            summary["neighbor_count"] = neighbor_count
            summary["details"] = row.get("neighbors", [])[:10]
            summary["is_sparse"] = neighbor_count < 4
            summary["mode"] = "full" if neighbor_count >= 4 else "fallback"
    except Exception as exc:  # pragma: no cover - defensive runtime guard for demo environments
        logger.warning("graph_context_summary_unavailable: %s", exc)

    return summary


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


if __name__ == "__main__":
    print("[RETRAINED BENCHMARK] GraphSAGE on data/processed/ splits, apples-to-apples vs production 72f XGBoost...")
    print("  - Node set: BTC-labeled wallets from processed train/val/test")
    print("  - XGBoost arms: 72-feature baseline vs 88-feature (72 + 16 GraphSAGE embeddings)")
    print("  - Fit: per-chain sample_weight from processed train.csv (exactly like train_combined_model)")
    print()
    benchmark = run_retrained_graphsage_benchmark()
    print(json.dumps(benchmark, indent=2, default=str))
