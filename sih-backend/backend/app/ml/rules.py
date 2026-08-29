"""
app/ml/rules.py — Rule-based laundering/layering detection (Phase 4).

v1 implementation per PRD §12:
  - Fan-out detection (many outgoing txs in short window)
  - Fan-in detection (many incoming senders in short window)
  - Peel-chain detection (repeated small % splits)
  - Louvain community detection + PageRank for hub wallets
  
Start with the rule engine — it's fast, explainable, and demo-safe.
Stretch: Temporal GNN (EvolveGCN) on Elliptic++.
Phase 0: stub.
"""


def detect_laundering_patterns(wallet_data: dict) -> list[str]:
    """
    Phase 4: apply rule engine to wallet transaction data.
    Returns a list of detected pattern names (e.g., ['fan_out', 'peel_chain']).
    """
    raise NotImplementedError("Laundering rule engine implemented in Phase 4.")
