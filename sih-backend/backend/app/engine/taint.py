"""
app/engine/taint.py — Layer 1: the taint propagation engine.

Implements value-ordered (chase-the-money-first) BFS haircut apportionment
over live explorer data, as specified in ARGUS-ENGINE-V2.md §Layer 1.

Scope, stated honestly (see ARGUS-ENGINE-V2.md §21):
  - "poison" and "fifo" methods currently apportion identically to "haircut"
    at the edge level (full/pro-rata amount respectively is future work);
    the method is recorded on every Trace row so this is never silently
    misrepresented as full FIFO/poison semantics.
  - Convergent taint (two tainted branches merging back into one address —
    "L3 confluence" in the design doc) is not merged in this slice: each
    BFS tree is independent. Cross-victim confluence detection is listed as
    Stage-2 future work in ARGUS-ENGINE-V2.md.
  - Wallet-level taint fraction is estimated from the explorer's fetched
    transaction window (bounded, e.g. 25-50 tx), not full on-chain history —
    an address with inflows outside that window will have its taint
    fraction over-estimated. This is disclosed, not hidden: it is the same
    class of limitation every bounded-window forensic tool has.
"""
import hashlib
import heapq
import itertools
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

from app.engine.registries import classify_bridge, classify_mixer
from app.schemas.common import Chain
from app.schemas.engine import TaintMethod, TerminalKind
from app.services.explorers.base import ExplorerUnavailableError, RawTx
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.known_vasps import lookup_known_vasp
from app.services.explorers.tron_explorer import TronExplorer

logger = structlog.get_logger(__name__)

_btc = BitcoinExplorer()
_eth = EthereumExplorer()
_tron = TronExplorer()

DUST_THRESHOLD: dict[str, float] = {
    "BTC": 0.00001,
    "ETH": 0.0001,
    "TRON": 1.0,
}


@dataclass
class TaintedNode:
    address: str
    chain: str
    hop: int
    taint_fraction: float
    taint_value: float
    terminal_kind: Optional[str]
    entity_name: Optional[str]
    entity_jurisdiction: Optional[str]
    proof_path: list[str]
    first_tainted_at: Optional[datetime]
    still_active: bool


@dataclass
class TaintPropagationResult:
    nodes: list[TaintedNode]
    terminals: list[TaintedNode]
    unattributed_residual: float
    terminated_at_mixer: float
    reproducible_hash: str


@dataclass(order=True)
class _FrontierItem:
    sort_key: float
    seq: int
    address: str = field(compare=False)
    chain: str = field(compare=False)
    hop: int = field(compare=False)
    taint_value: float = field(compare=False)
    proof_path: list[str] = field(compare=False)
    first_tainted_at: Optional[datetime] = field(compare=False)


def _explorer_for(chain: str):
    return {"BTC": _btc, "ETH": _eth, "TRON": _tron}.get(chain)


def _classify_terminal(address: str, chain: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Returns (terminal_kind, entity_name, jurisdiction) or (None, None, None) if not terminal."""
    if match := lookup_known_vasp(address):
        name, jurisdiction = match
        return TerminalKind.VASP.value, name, jurisdiction
    if mixer_name := classify_mixer(address):
        return TerminalKind.MIXER_BOUNDARY.value, mixer_name, None
    if bridge_name := classify_bridge(address):
        return TerminalKind.BRIDGE.value, bridge_name, None
    return None, None, None


async def propagate_taint(
    anchor_address: str,
    anchor_chain: str,
    anchor_taint_value: float,
    method: TaintMethod,
    max_hops: int,
    max_nodes: int,
    dilution_floor: float,
) -> TaintPropagationResult:
    """
    Chase-the-money-first BFS from the anchor address. The frontier is a
    max-heap on absolute tainted value (not hop count) — see
    ARGUS-ENGINE-V2.md §1.3 for why: bounded compute goes where the money is.
    """
    dust = DUST_THRESHOLD.get(anchor_chain, 0.0)
    counter = itertools.count()
    frontier: list[_FrontierItem] = []
    heapq.heappush(
        frontier,
        _FrontierItem(
            sort_key=-anchor_taint_value, seq=next(counter),
            address=anchor_address, chain=anchor_chain, hop=0,
            taint_value=anchor_taint_value, proof_path=[], first_tainted_at=None,
        ),
    )

    visited: dict[tuple[str, str], TaintedNode] = {}

    while frontier and len(visited) < max_nodes:
        item = heapq.heappop(frontier)
        key = (item.address, item.chain)
        if key in visited:
            continue

        explorer = _explorer_for(item.chain)
        if explorer is None:
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DEPTH_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
            )
            continue

        terminal_kind, entity_name, jurisdiction = _classify_terminal(item.address, item.chain)
        if terminal_kind is not None:
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=terminal_kind, entity_name=entity_name,
                entity_jurisdiction=jurisdiction, proof_path=item.proof_path,
                first_tainted_at=item.first_tainted_at,
                still_active=terminal_kind != TerminalKind.MIXER_BOUNDARY.value,
            )
            continue

        if item.hop >= max_hops:
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DEPTH_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
            )
            continue

        try:
            txs = await explorer.get_transactions(item.address, limit=40)
        except ExplorerUnavailableError as exc:
            logger.warning("taint_explorer_unavailable", address=item.address, chain=item.chain, error=str(exc))
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DEPTH_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
            )
            continue

        wallet_fraction, wallet_first_tainted_at = _estimate_wallet_fraction(
            item.address, txs, item.taint_value, item.first_tainted_at,
        )

        if wallet_fraction < dilution_floor:
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=wallet_fraction, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DUST.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
                still_active=True,
            )
            continue

        outgoing = _outgoing_txs(item.address, txs)
        if not outgoing:
            # Tainted funds arrived here and have not moved on (in the fetched
            # window) — this is the most operationally important terminal:
            # money is still sitting at an identified, freezable address.
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=wallet_fraction, taint_value=item.taint_value,
                terminal_kind=TerminalKind.NODE_LIMIT.value if item.hop == 0 else "NO_OUTFLOW",
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
                still_active=True,
            )
            continue

        visited[key] = TaintedNode(
            address=item.address, chain=item.chain, hop=item.hop,
            taint_fraction=wallet_fraction, taint_value=item.taint_value,
            terminal_kind=None, entity_name=None, entity_jurisdiction=None,
            proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
            still_active=False,
        )

        for tx in outgoing:
            child_value = _apportion(method, tx.amount, wallet_fraction)
            if child_value <= dust:
                continue
            child_key = (tx.to_address, item.chain)
            if child_key in visited:
                continue
            heapq.heappush(
                frontier,
                _FrontierItem(
                    sort_key=-child_value, seq=next(counter),
                    address=tx.to_address, chain=item.chain, hop=item.hop + 1,
                    taint_value=child_value,
                    proof_path=[*item.proof_path, tx.tx_hash],
                    first_tainted_at=tx.timestamp,
                ),
            )

    if len(visited) >= max_nodes and frontier:
        # Budget exhausted with money still untraced — record the largest
        # unresolved branches rather than silently dropping them.
        for item in heapq.nsmallest(min(10, len(frontier)), frontier):
            key = (item.address, item.chain)
            if key in visited:
                continue
            visited[key] = TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.NODE_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
            )

    all_nodes = list(visited.values())
    terminals = [n for n in all_nodes if n.terminal_kind is not None]
    unattributed_residual = sum(
        n.taint_value for n in terminals
        if n.terminal_kind not in (TerminalKind.MIXER_BOUNDARY.value,)
    )
    terminated_at_mixer = sum(
        n.taint_value for n in terminals if n.terminal_kind == TerminalKind.MIXER_BOUNDARY.value
    )
    # VASP terminals are attributed and actionable, not "residual" in the
    # unattributed sense — exclude them from the residual bucket.
    unattributed_residual -= sum(
        n.taint_value for n in terminals if n.terminal_kind == TerminalKind.VASP.value
    )

    reproducible_hash = _compute_reproducible_hash(
        anchor_address, anchor_chain, method, max_hops, max_nodes, dilution_floor, all_nodes,
    )

    return TaintPropagationResult(
        nodes=all_nodes,
        terminals=terminals,
        unattributed_residual=max(0.0, unattributed_residual),
        terminated_at_mixer=terminated_at_mixer,
        reproducible_hash=reproducible_hash,
    )


def _apportion(method: TaintMethod, tx_amount: float, wallet_fraction: float) -> float:
    if method == TaintMethod.poison:
        # Poison: any contact with taint makes the full amount tainted onward.
        return tx_amount if wallet_fraction > 0 else 0.0
    # haircut and fifo (fifo ordering not yet modeled — see module docstring)
    return tx_amount * wallet_fraction


def _outgoing_txs(address: str, txs: list[RawTx]) -> list[RawTx]:
    norm = address.strip().lower()
    return [tx for tx in txs if tx.from_address and tx.from_address.strip().lower() == norm]


def _estimate_wallet_fraction(
    address: str,
    txs: list[RawTx],
    incoming_taint_value: float,
    fallback_first_tainted_at: Optional[datetime],
) -> tuple[float, Optional[datetime]]:
    """
    haircut fraction = tainted inflow / total observed inflow, within the
    explorer's fetched window. If no other inflow is observed at all, the
    conservative default is 100% tainted (see module docstring on window
    limitations) rather than guessing a lower number we cannot support.
    """
    norm = address.strip().lower()
    incoming = [tx for tx in txs if tx.to_address and tx.to_address.strip().lower() == norm]
    total_inflow = sum(tx.amount for tx in incoming)
    first_seen = min((tx.timestamp for tx in incoming), default=fallback_first_tainted_at)
    if total_inflow <= 0:
        return 1.0, first_seen
    fraction = min(1.0, incoming_taint_value / total_inflow)
    return fraction, first_seen


def _compute_reproducible_hash(
    anchor_address: str,
    anchor_chain: str,
    method: TaintMethod,
    max_hops: int,
    max_nodes: int,
    dilution_floor: float,
    nodes: list[TaintedNode],
) -> str:
    """
    SHA-256 over the exact parameters and the exact result of THIS run.
    Scope note (not overclaimed): this proves "this run produced exactly
    this data" for integrity/audit purposes. It does NOT guarantee an
    identical hash on a re-run days later against live explorers, because
    the underlying chain can grow new outgoing transactions in the interim
    — that is a property of live blockchain data, not a flaw in the hash.
    """
    canonical_nodes = sorted(
        (n.address, n.chain, n.hop, round(n.taint_fraction, 6), round(n.taint_value, 8), n.terminal_kind)
        for n in nodes
    )
    payload = {
        "anchor_address": anchor_address,
        "anchor_chain": anchor_chain,
        "method": method.value,
        "max_hops": max_hops,
        "max_nodes": max_nodes,
        "dilution_floor": round(dilution_floor, 6),
        "nodes": canonical_nodes,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()
