"""app/tests/test_embedding_store.py — Tests for the live GraphSAGE embedding store."""
import numpy as np
import pytest

from app.ml.embedding_store import EMBEDDING_DIM, get_live_embeddings, lookup_embedding
from app.ml.features import GSAGE_EMBEDDING_COLUMNS, MODEL_FEATURE_COLUMNS


def test_lookup_embedding_unknown_returns_zeros():
    """Fresh/unknown address gets a 16-dim zero vector (zero fallback)."""
    emb = lookup_embedding("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    assert emb.shape == (EMBEDDING_DIM,)
    assert emb.dtype == np.float32
    assert np.abs(emb).sum() == 0.0


def test_lookup_embedding_known_is_nonzero_and_lowercase_insensitive():
    """A real in-graph BTC address returns its stored 16-dim embedding."""
    from app.ml.embedding_store import _load_store
    store = _load_store()
    assert store, "embedding store should be non-empty"
    some_addr = next(iter(store))
    emb = lookup_embedding(some_addr)
    assert emb.shape == (EMBEDDING_DIM,)
    assert np.abs(emb).sum() > 0.0


def test_embedding_dim_matches_feature_schema():
    """The embedding store dim must match the 16 GSAGE columns of the 92f schema."""
    assert EMBEDDING_DIM == len(GSAGE_EMBEDDING_COLUMNS)
    # 72 tabular/graph + 16 embeddings + 4 relative features = 92
    assert len(GSAGE_EMBEDDING_COLUMNS) + 76 == len(MODEL_FEATURE_COLUMNS)


@pytest.mark.asyncio
async def test_get_live_embeddings_returns_tuple_fallback():
    """Async live lookup returns (embedding, mode). Unknown/ETH -> fallback."""
    emb, mode = await get_live_embeddings("0xde0B295669a9FD93d5F28D9Ec85E40f4cb697BAe", "ETH")
    assert emb.shape == (EMBEDDING_DIM,)
    assert mode == "fallback"
    assert np.abs(emb).sum() == 0.0