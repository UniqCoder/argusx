"""
app/engine/clustering.py — Grouping wallets that one operator plausibly controls.

`Wallet.cluster_id` has existed in the schema since Phase 0 with nothing that
ever wrote it. This writes it, from two heuristics that need no data beyond the
trace itself:

  SHARED DEPOSIT     several traced wallets pay the same exchange deposit
                     address. Deposit addresses are issued per customer
                     account, so wallets funding one are very likely one
                     account — this is the strongest signal available here.

  COMMON FUNDING     several wallets funded by the same parent, in near-equal
                     amounts, inside a short window. That is a split, not a
                     coincidence: the shape is what structuring looks like.

WHAT THIS IS NOT
----------------
Not common-input-ownership (that needs per-input UTXO data these explorers do
not return), and not a commercial attribution dataset. Every cluster carries
the rule that produced it, so a reader can judge it instead of trusting a
coloured blob. Two wallets in one cluster means "these behave as one operator
in this trace", not "these are proven to share a private key".
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional


# How close two sibling payments must be in size to read as one split rather
# than two unrelated payments.
SIBLING_VALUE_SPREAD = 0.12
# And how close in time.
SIBLING_WINDOW = timedelta(minutes=30)
# Below this many members it is a pair of transactions, not a pattern.
MIN_CLUSTER_SIZE = 2


@dataclass
class Cluster:
    id: str
    label: str
    basis: str
    members: list[tuple[str, str]]  # (address, chain)


def _cluster_id(seed: str) -> str:
    return "cl_" + hashlib.sha256(seed.encode()).hexdigest()[:12]


def detect(nodes: list) -> tuple[dict[tuple[str, str], Cluster], list[Cluster]]:
    """
    Returns (annotation-by-node-key, clusters). Keys are (lowercased address, chain).
    """
    key = lambda n: (n.address.lower(), n.chain)  # noqa: E731
    by_key = {key(n): n for n in nodes}
    clusters: list[Cluster] = []
    assigned: dict[tuple[str, str], Cluster] = {}

    # ── 1. Shared exchange deposit ──────────────────────────────────────────
    # Who pays each VASP terminal? A VASP address is settled once (taint at an
    # address is only counted once), so every OTHER payer's edge lives in
    # `convergent_parents`, not as a second node with its own parent_address --
    # both sources have to be read or a fourth smurf paying the same exchange
    # deposit as three others would silently miss the cluster.
    payers_by_vasp: dict[tuple[str, str], list] = {}
    for n in nodes:
        if n.terminal_kind != "VASP":
            continue
        if n.parent_address:
            parent = next(
                (m for m in nodes if m.address.lower() == n.parent_address.lower()), None
            )
            if parent is not None:
                payers_by_vasp.setdefault(key(n), []).append(parent)
        for edge in getattr(n, "convergent_parents", []) or []:
            parent = next(
                (m for m in nodes if m.address.lower() == edge["address"].lower()), None
            )
            if parent is not None:
                payers_by_vasp.setdefault(key(n), []).append(parent)

    for vasp_key, payers in payers_by_vasp.items():
        unique = {key(p): p for p in payers}
        if len(unique) < MIN_CLUSTER_SIZE:
            continue
        vasp = by_key[vasp_key]
        cluster = Cluster(
            id=_cluster_id(f"deposit|{vasp_key[0]}|{vasp_key[1]}"),
            label=f"{vasp.entity_name or 'Exchange'} deposit cluster — {len(unique)} wallets",
            basis=(
                f"{len(unique)} traced wallets paid into the same "
                f"{vasp.entity_name or 'exchange'} deposit address. Deposit addresses are "
                f"issued per customer account, so these wallets very likely fund one account."
            ),
            members=list(unique.keys()),
        )
        clusters.append(cluster)
        for mk in unique:
            assigned.setdefault(mk, cluster)

    # ── 2. Common funding, near-equal, close in time ────────────────────────
    siblings_by_parent: dict[str, list] = {}
    for n in nodes:
        if n.parent_address:
            siblings_by_parent.setdefault(n.parent_address.lower(), []).append(n)

    for parent_addr, siblings in siblings_by_parent.items():
        group = [s for s in siblings if s.tx_amount]
        if len(group) < 3:  # a split needs to look like a split
            continue
        amounts = [s.tx_amount for s in group]
        spread = (max(amounts) - min(amounts)) / max(amounts) if max(amounts) else 1.0
        times = [s.first_tainted_at for s in group if s.first_tainted_at]
        window = (max(times) - min(times)) if len(times) >= 2 else None
        if spread > SIBLING_VALUE_SPREAD:
            continue
        if window is not None and window > SIBLING_WINDOW:
            continue

        members = [key(s) for s in group if key(s) not in assigned]
        if len(members) < MIN_CLUSTER_SIZE:
            continue
        minutes = window.total_seconds() / 60.0 if window else None
        cluster = Cluster(
            id=_cluster_id(f"split|{parent_addr}"),
            label=f"Structuring split — {len(members)} wallets",
            basis=(
                f"{len(group)} wallets were funded by the same address in amounts within "
                f"{spread * 100:.1f}% of each other"
                + (f", all inside {minutes:.0f} minutes" if minutes is not None else "")
                + ". One sum split evenly, not several unrelated payments."
            ),
            members=members,
        )
        clusters.append(cluster)
        for mk in members:
            assigned.setdefault(mk, cluster)

    return assigned, clusters


def apply_to(annotations: dict, nodes: list) -> list[Cluster]:
    """Attach detected clusters onto existing NodeAnnotations, in place."""
    assigned, clusters = detect(nodes)
    for node_key, cluster in assigned.items():
        ann = annotations.get(node_key)
        if ann is not None:
            ann.cluster_id = cluster.id
            ann.cluster_label = cluster.label
    return clusters
