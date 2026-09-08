"""
app/ml/embedding_store.py — Live GraphSAGE embedding lookup with zero fallback.

The production /risk path derives the 16 embedding features from a precomputed
store (`wallet_embeddings.npz`): 16-dim SAGE embeddings for all 265,354
BTC-labeled graph nodes from the retrained encoder (seed=42), matching the 88f
offline benchmark exactly.

Addresses NOT present in the store (fresh/unseen addresses, ETH rows, timeouts)
receive a 16-dim zero vector, mirroring the is_sparse/fallback pattern used by
``app/ml/live_graph_features.py``.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

_ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
EMBEDDING_PATH = os.path.join(_ARTIFACTS_DIR, "wallet_embeddings.npz")
EMBEDDING_DIM = 16

_store: Optional[dict[str, np.ndarray]] = None


def _load_store() -> dict[str, np.ndarray]:
    """Lazily load the embedding store once. Returns {lowercased_address: (16,) float32}."""
    global _store
    if _store is not None:
        return _store
    if not os.path.exists(EMBEDDING_PATH):
        logger.warning("embedding_store_missing", extra={"path": EMBEDDING_PATH})
        _store = {}
        return _store
    data = np.load(EMBEDDING_PATH)
    addresses = data["addresses"]
    embeddings = data["embeddings"]
    if addresses.dtype.kind == "S":
        addresses = np.char.decode(addresses, "utf-8")
    _store = {str(a): embeddings[i].astype(np.float32) for i, a in enumerate(addresses)}
    logger.info("embedding_store_loaded", extra={"node_count": len(_store), "dim": EMBEDDING_DIM})
    return _store


def lookup_embedding(address: str) -> np.ndarray:
    """Return the 16-dim embedding for ``address`` or a zero vector if not in the store."""
    store = _load_store()
    key = str(address).strip().lower()
    emb = store.get(key)
    if emb is None:
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32)
    return emb


async def get_live_embeddings(address: str, chain: str, timeout_seconds: float = 2.0) -> tuple[np.ndarray, str]:
    """Async live embedding lookup with the same timeout+fallback contract as
    ``compute_live_graph_features_with_fallback``.

    Returns (embedding_row (16,), mode) where mode is:
      - "full"     found graph node, non-zero embedding
      - "fallback" known-empty (address not in the embedding store)
      - "failed"   timeout — lookup could not complete (zeros, explicitly tagged)

    Non-timeout failures propagate to the caller (never silently zeroed here).
    """
    loop = asyncio.get_running_loop()

    async def _compute() -> tuple[np.ndarray, str]:
        emb = await loop.run_in_executor(None, lookup_embedding, address)
        if np.abs(emb).sum() > 0:
            return emb, "full"
        return emb, "fallback"

    try:
        return await asyncio.wait_for(_compute(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.warning("embedding_computation_timed_out", extra={"address": address, "chain": chain})
        return np.zeros((EMBEDDING_DIM,), dtype=np.float32), "failed"