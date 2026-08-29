"""
app/ml/clustering.py — Address clustering (Phase 4).

BTC: UTXO co-spend heuristic (near-free, high precision)
ETH/TRON: Node2Vec/GraphSAGE embeddings → HDBSCAN
Phase 0: stub.
"""


async def cluster_wallets(addresses: list[str], chain: str) -> dict[str, str]:
    """
    Phase 4: cluster wallet addresses and return {address: cluster_id} mapping.
    """
    raise NotImplementedError("Address clustering implemented in Phase 4.")
