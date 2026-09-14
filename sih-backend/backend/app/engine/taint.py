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
import asyncio
import hashlib
import heapq
import itertools
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import structlog

from app.engine.clustering import apply_to as apply_clusters
from app.engine.crosschain import resolve_crossing
from app.engine.roles import annotate as annotate_roles
from app.engine.typologies import detect as detect_typologies
from app.engine.typologies import summarize_path_risk
from app.engine.registries import classify_bridge, classify_mixer
from app.schemas.common import Chain
from app.schemas.engine import TaintMethod, TerminalKind
from app.services.explorers import tx_cache as tx_cache_store
from app.services.explorers.base import ExplorerUnavailableError, RawTx
from app.services.explorers.btc_explorer import BitcoinExplorer
from app.services.explorers.eth_explorer import EthereumExplorer
from app.services.explorers.known_vasps import lookup_known_vasp
from app.services.explorers.tron_explorer import TronExplorer
from app.services.scenarios.definitions import is_scenario_address, scenario_for_address
from app.services.scenarios.fixture_explorer import FixtureExplorer, fixture_explorer_for

logger = structlog.get_logger(__name__)

_btc = BitcoinExplorer()
_eth = EthereumExplorer()
_tron = TronExplorer()

# Native-coin dust floors, per chain.
DUST_THRESHOLD: dict[str, float] = {
    "BTC": 0.00001,
    "ETH": 0.0001,
    "TRON": 1.0,
}

# Dust floors for traced TOKEN assets. A chain's native floor is meaningless
# for a token: 0.0001 is a sane "not worth chasing" amount of ETH (~$0.30) but
# 0.0001 USDT is a hundredth of a cent, while 1.0 (TRON's native floor) would
# throw away a whole dollar of USDT. Keyed by ticker, value in whole units of
# that token.
ASSET_DUST_THRESHOLD: dict[str, float] = {
    "USDT": 0.01,
    "USDC": 0.01,
    "DAI": 0.01,
    "BUSD": 0.01,
    "TUSD": 0.01,
    "WETH": 0.0001,
    "WBTC": 0.00001,
}


def _dust_for(asset: Optional[str], chain: str) -> float:
    """Dust floor for the asset actually being traced, not just for the chain."""
    if asset and asset in ASSET_DUST_THRESHOLD:
        return ASSET_DUST_THRESHOLD[asset]
    if asset and asset not in (chain, "ETH", "BTC", "TRX"):
        # An unrecognised token: fall back to a small nominal floor rather than
        # the native-coin floor, which can be orders of magnitude off.
        return 0.0
    return DUST_THRESHOLD.get(chain, 0.0)


NATIVE_TICKER: dict[str, str] = {"ETH": "ETH", "BTC": "BTC", "TRON": "TRX"}


def _recognized_assets(chain: str) -> set[str]:
    """
    The asset universe ARGUS actually has a dust floor and evidentiary story
    for: the chain's native coin plus the major stablecoins/wrapped assets in
    ASSET_DUST_THRESHOLD. Used to pick which asset a trace follows without
    that choice being hijacked by an unsolicited spam-token airdrop.
    """
    return {*ASSET_DUST_THRESHOLD.keys(), NATIVE_TICKER.get(chain, chain)}

# How many "branch left unresolved" markers may be emitted when the node
# budget runs out with money still moving. Reserved out of max_nodes rather
# than added on top of it, so max_nodes is a real cap.
_UNRESOLVED_MARKERS = 10


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
    # The specific incoming edge that reached this node — None only for the
    # anchor (hop 0), which has no parent. Needed to render the real
    # branching money-flow graph (multiple children per node), not just a
    # flat hop list.
    parent_address: Optional[str] = None
    tx_hash: Optional[str] = None
    tx_amount: Optional[float] = None
    # Onward transfers from this address that were NOT followed because their
    # apportioned value was at or below the dust threshold.
    pruned_child_count: int = 0
    pruned_child_value: float = 0.0
    # Onward transfers in a DIFFERENT asset than the one being traced. These
    # are real money movements, not dust — they are simply outside this run's
    # asset scope, and conflating them with dust (which is what happened
    # before the engine knew about assets) hid stablecoin outflows entirely.
    other_asset_child_count: int = 0
    # How this node's INBOUND edge was established:
    #   "ON_CHAIN"                 a signed transaction on one chain (the default)
    #   "CROSS_CHAIN_HEURISTIC"    a bridge deposit matched to a release on
    #                              another chain by value and time
    # These are not the same kind of evidence and the UI must never draw them
    # the same way. See app/engine/crosschain.py.
    link_basis: str = "ON_CHAIN"
    link_confidence: Optional[float] = None
    link_detail: Optional[str] = None
    # Filled by a post-pass over the finished graph (app/engine/roles.py and
    # app/engine/clustering.py). Not part of propagation, and deliberately not
    # part of the reproducible hash: these are a reading of the graph, and a
    # better reading later must not change what the trace itself attests to.
    role: Optional[str] = None
    role_basis: Optional[str] = None
    description: Optional[str] = None
    cluster_id: Optional[str] = None
    cluster_label: Optional[str] = None
    value_in: float = 0.0
    value_out: float = 0.0
    value_parked: float = 0.0
    # Other payments into this SAME address, arriving after it was already
    # settled (a second victim's fan-in to one collector, several smurfs
    # cashing out to one exchange deposit). `visited` is keyed by (address,
    # chain) because taint can only be counted at an address once -- but that
    # means a later arrival's edge used to be silently dropped, so a wallet
    # paying into an already-terminal VASP address looked like a dead-end mule
    # instead of a cash-out. Recorded here so roles/clustering can see the
    # real fan-in without double-counting taint.
    convergent_parents: list[dict] = field(default_factory=list)


@dataclass
class InboundSource:
    """
    A wallet observed paying INTO the anchor.

    The BFS only walks forwards, from the reported address outwards, so the
    victim side of a case was structurally invisible: the graph could show
    where the money went but never who it came from. These are read from the
    anchor's own transaction window at hop 0 — the same data the seed is
    resolved from — and are reported separately from `nodes` so they cost no
    node budget, change no taint arithmetic, and do not enter the
    reproducible hash. They are context, not propagation.
    """
    address: str
    chain: str
    amount: float
    asset: str
    tx_hash: str
    timestamp: Optional[datetime] = None


@dataclass
class TaintPropagationResult:
    nodes: list[TaintedNode]
    terminals: list[TaintedNode]
    unattributed_residual: float
    terminated_at_mixer: float
    reproducible_hash: str
    depth_reached: int = 0
    termination_reason: str = "frontier_exhausted"
    seed_value: float = 0.0
    seed_basis: str = "observed_inflow"
    pruned_branch_count: int = 0
    pruned_branch_value: float = 0.0
    # The single asset this trace followed, and how it was chosen. Taint is
    # apportioned per asset: a haircut fraction of tainted-inflow / total-inflow
    # is only meaningful when both are denominated in the same thing.
    asset: str = ""
    asset_basis: str = "dominant_inflow"
    other_asset_branch_count: int = 0
    # Where the transaction data came from. Asserted by the engine, never
    # inferred by the client: a seeded scenario must not be able to look like a
    # live trace on any screen, and the client guessing from an address prefix
    # is exactly the kind of check that quietly stops matching.
    #   live            every address answered by a public explorer
    #   seeded_scenario every address answered by the scenario fixture
    #   mixed           both (a scenario whose trail reaches a live address)
    data_source: str = "live"
    scenario_key: Optional[str] = None
    # Wallets observed funding the anchor. See InboundSource.
    inbound_sources: list["InboundSource"] = field(default_factory=list)
    # Groups of wallets one operator plausibly controls, each with the rule
    # that produced it. See app/engine/clustering.py.
    clusters: list[dict] = field(default_factory=list)
    # Laundering patterns this trace exhibits, and a plain-language path-risk
    # summary. See app/engine/typologies.py. Explanation, never a decision
    # input -- app/engine/decision.py never reads this.
    typologies: list[dict] = field(default_factory=list)
    path_risk: dict = field(default_factory=dict)


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
    parent_address: Optional[str] = field(compare=False, default=None)
    tx_hash: Optional[str] = field(compare=False, default=None)
    tx_amount: Optional[float] = field(compare=False, default=None)
    link_basis: str = field(compare=False, default="ON_CHAIN")
    link_confidence: Optional[float] = field(compare=False, default=None)
    link_detail: Optional[str] = field(compare=False, default=None)


_LIVE_EXPLORERS = {"BTC": _btc, "ETH": _eth, "TRON": _tron}


def _explorer_for(chain: str, address: str = ""):
    """
    Pick the data source for one address.

    Seeded-scenario addresses (app/services/scenarios/) are answered from a
    local fixture; everything else goes to the real public explorer for that
    chain, unchanged. The check is on (address, chain), not chain alone, so a
    live ETH trace is never diverted -- and POLYGON, which has no live explorer,
    is walkable only where a scenario supplies its transactions.
    """
    if address and is_scenario_address(address, chain):
        return fixture_explorer_for(chain)
    return _LIVE_EXPLORERS.get(chain)


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


# An optional observer for a trace in progress. Purely additive: when None,
# propagation behaves exactly as it always has, and the synchronous endpoint and
# every existing test are unaffected.
#
# Events are emitted as nodes are SETTLED, in the engine's own value-ordered
# sequence. Nothing about ordering, the node budget or `reproducible_hash`
# depends on whether anyone is listening — the observer watches, it never
# steers. That property is what makes it safe to stream a forensic trace.
TraceEventSink = Callable[[str, dict], Awaitable[None]]


async def propagate_taint(
    anchor_address: str,
    anchor_chain: str,
    anchor_taint_value: Optional[float],
    method: TaintMethod,
    max_hops: int,
    max_nodes: int,
    dilution_floor: float,
    on_event: Optional["TraceEventSink"] = None,
    complaint_count: int = 0,
) -> TaintPropagationResult:
    """
    Chase-the-money-first BFS from the anchor address. The frontier is a
    max-heap on absolute tainted value (not hop count) — see
    ARGUS-ENGINE-V2.md §1.3 for why: bounded compute goes where the money is.

    `anchor_taint_value` is the tainted seed in the chain's native unit. Pass
    the real amount when the complaint states one. Pass None to seed from the
    anchor address's own observed inflow — i.e. treat every unit of value that
    arrived at the reported address as tainted, which is the conservative
    forensic default. It must never be a fixed placeholder: this parameter was
    hardcoded to 1.0 at the only production call site, which meant the engine
    silently assumed "exactly 1.0 ETH/BTC/TRX was stolen" on every single
    trace and every downstream taint_fraction was arithmetic on that invented
    number.

    `max_nodes` is a hard cap on the total number of nodes returned. Part of
    the budget is reserved for markers describing branches left unresolved
    when the cap is hit, so the result can say "money was still moving here"
    without exceeding the cap the caller asked for (it previously overshot —
    a requested 40 returned 48).
    """
    # Provisional until the anchor's asset is known (resolved on the first
    # iteration); recomputed as `dust` below once `asset` is set.
    dust = DUST_THRESHOLD.get(anchor_chain, 0.0)
    # Reserve part of the budget for "unresolved branch" markers so the total
    # never exceeds max_nodes.
    marker_budget = min(_UNRESOLVED_MARKERS, max(0, max_nodes // 5))
    expansion_budget = max(1, max_nodes - marker_budget)
    seed_basis = "reported_amount" if anchor_taint_value is not None else "observed_inflow"
    seed_value = anchor_taint_value
    pruned_branch_count = 0
    pruned_branch_value = 0.0
    # Resolved at the anchor from its real activity (see the BFS body).
    asset: Optional[str] = None
    asset_basis = "dominant_inflow"
    other_asset_branch_count = 0
    counter = itertools.count()
    frontier: list[_FrontierItem] = []
    # When the seed is unknown it is resolved from the anchor's observed inflow
    # once its transactions are fetched below; math.inf here just guarantees the
    # anchor is popped first (it is the only item on the frontier anyway).
    heapq.heappush(
        frontier,
        _FrontierItem(
            sort_key=-(anchor_taint_value if anchor_taint_value is not None else float("inf")),
            seq=next(counter),
            address=anchor_address, chain=anchor_chain, hop=0,
            taint_value=anchor_taint_value if anchor_taint_value is not None else 0.0,
            proof_path=[], first_tainted_at=None,
            parent_address=None, tx_hash=None, tx_amount=None,
        ),
    )

    visited: dict[tuple[str, str], TaintedNode] = {}
    # Per-trace transaction-window cache, filled by the speculative prefetch
    # below. Keyed by (address, chain) so an address is never fetched twice in
    # one trace.
    tx_cache: dict[tuple[str, str], list[RawTx]] = {}
    # Addresses the concurrent prefetch already found unreachable, within THIS
    # trace. The prefetch swallows its failures, so without this the main loop
    # re-ran the explorer's entire retry sequence for the same address moments
    # later: measured at 34s of a 34s trace, spent twice on one timing-out
    # address (8s timeout + 1s backoff + 8s timeout, done twice). Re-asking does
    # not make the answer more true — it is the same outage, seconds apart.
    tx_failures: dict[tuple[str, str], str] = {}

    async def settle(k: tuple[str, str], n: TaintedNode) -> None:
        """Record a finished node and, if anyone is watching, report it."""
        visited[k] = n
        if on_event is not None:
            await on_event("node", _node_event(n, len(visited)))
    sourced_from_fixture = False
    sourced_from_live = False
    inbound_sources: list[InboundSource] = []

    while frontier and len(visited) < expansion_budget:
        await _prefetch_frontier(frontier, visited, tx_cache, tx_failures)
        item = heapq.heappop(frontier)
        key = (item.address, item.chain)
        if key in visited:
            # A second (or third...) payment into an address already settled.
            # Not re-expanded -- taint at an address is counted once -- but the
            # edge is real and is kept so roles/clustering can see the fan-in.
            if item.parent_address and item.tx_hash:
                visited[key].convergent_parents.append({
                    "address": item.parent_address, "chain": item.chain,
                    "tx_hash": item.tx_hash, "tx_amount": item.tx_amount,
                    "first_tainted_at": item.first_tainted_at,
                })
            continue

        explorer = _explorer_for(item.chain, item.address)
        if explorer is not None:
            if isinstance(explorer, FixtureExplorer):
                sourced_from_fixture = True
            else:
                sourced_from_live = True
        if explorer is None:
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DEPTH_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        terminal_kind, entity_name, jurisdiction = _classify_terminal(item.address, item.chain)

        # A bridge is still a terminal — the money genuinely stops being
        # traceable on THIS chain there. But where the release on the other side
        # can be matched by value and time, the trail continues, clearly marked
        # as the correlation it is. Without this an ETH -> bridge -> exchange
        # trail ends at a contract and the exchange deposit is never found.
        if terminal_kind == TerminalKind.BRIDGE.value and item.hop < max_hops:
            link = await resolve_crossing(
                bridge_address=item.address,
                source_chain=item.chain,
                deposit_amount=item.tx_amount if item.tx_amount is not None else item.taint_value,
                deposit_at=item.first_tainted_at,
                asset=asset,
                fetch_transactions=_fetch_for_crosschain,
            )
            if link is not None and (link.to_address, link.to_chain) not in visited:
                heapq.heappush(
                    frontier,
                    _FrontierItem(
                        sort_key=-min(item.taint_value, link.amount),
                        seq=next(counter),
                        address=link.to_address, chain=link.to_chain, hop=item.hop + 1,
                        # Value is capped at what actually came out the other
                        # side: a bridge fee is value that left the trail, not
                        # value that moved on.
                        taint_value=min(item.taint_value, link.amount),
                        proof_path=[*item.proof_path, link.tx_hash],
                        first_tainted_at=link.timestamp,
                        parent_address=item.address, tx_hash=link.tx_hash,
                        tx_amount=link.amount,
                        link_basis=link.basis,
                        link_confidence=link.confidence,
                        link_detail=link.detail,
                    ),
                )

        if terminal_kind is not None:
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=terminal_kind, entity_name=entity_name,
                entity_jurisdiction=jurisdiction, proof_path=item.proof_path,
                first_tainted_at=item.first_tainted_at,
                still_active=terminal_kind != TerminalKind.MIXER_BOUNDARY.value,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        if item.hop >= max_hops:
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DEPTH_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        try:
            if key in tx_cache:
                txs = tx_cache.pop(key)
            elif key in tx_failures:
                raise ExplorerUnavailableError(tx_failures[key])
            else:
                txs = await _fetch_transactions(explorer, item.address, item.chain, TX_WINDOW)
        except ExplorerUnavailableError as exc:
            # Explorer outage (timeout / 5xx / rate-limit) at this node. NOT the
            # same as an honest depth/budget limit: this previously reused
            # DEPTH_LIMIT, which misreported "trace got too deep" when the
            # explorer was simply unreachable — hiding retryable outages as
            # completed traces. EXPLORER_UNAVAILABLE keeps the distinction.
            logger.warning("taint_explorer_unavailable", address=item.address, chain=item.chain, error=str(exc))
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.EXPLORER_UNAVAILABLE.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        # Pick the asset to trace, at the anchor. Value-tracing is only
        # coherent within one asset, so the run follows whichever asset the
        # reported address actually received the most of — for an Indian
        # task-fraud wallet that is typically USDT, not the native coin.
        if item.hop == 0 and asset is None:
            _self0 = item.address.strip().lower()
            recognized = _recognized_assets(anchor_chain)
            inflow_by_asset: dict[str, float] = {}
            for tx in txs:
                if tx.to_address and tx.to_address.strip().lower() == _self0:
                    key_asset = tx.asset or anchor_chain
                    inflow_by_asset[key_asset] = inflow_by_asset.get(key_asset, 0.0) + tx.amount
            # Rank only recognized assets (native coin + major stablecoins/
            # wrapped assets) first. Unsolicited "airdrop"/dust-spam tokens —
            # a routine address-poisoning tactic against any well-known wallet
            # — mint themselves in arbitrary, often huge, nominal quantities
            # with a made-up ticker. Ranking by raw inflow amount across ALL
            # tickers let one spam token outrank real ETH/USDT activity and
            # get chosen as "the" asset to trace, at which point a wallet that
            # never sends that spam token back out falsely reported
            # NO_OUTFLOW even while genuinely moving money in other assets.
            # Only fall back to the full (unrecognized-inclusive) ranking when
            # nothing recognized was received at all, so a case that genuinely
            # is about an obscure token can still trace.
            recognized_inflow = {a: v for a, v in inflow_by_asset.items() if a in recognized}
            if recognized_inflow:
                asset = max(recognized_inflow.items(), key=lambda kv: kv[1])[0]
                asset_basis = "dominant_inflow"
            elif inflow_by_asset:
                asset = max(inflow_by_asset.items(), key=lambda kv: kv[1])[0]
                asset_basis = "dominant_inflow_unrecognized_asset"
            else:
                # Nothing received in the window — fall back to the dominant
                # OUTGOING asset so a send-only wallet still traces.
                outflow_by_asset: dict[str, float] = {}
                for tx in txs:
                    if tx.from_address and tx.from_address.strip().lower() == _self0:
                        key_asset = tx.asset or anchor_chain
                        outflow_by_asset[key_asset] = outflow_by_asset.get(key_asset, 0.0) + tx.amount
                recognized_outflow = {a: v for a, v in outflow_by_asset.items() if a in recognized}
                ranked_outflow = recognized_outflow or outflow_by_asset
                if ranked_outflow:
                    asset = max(ranked_outflow.items(), key=lambda kv: kv[1])[0]
                    asset_basis = "dominant_outflow"
                else:
                    asset = anchor_chain
                    asset_basis = "no_activity"
            logger.info(
                "taint_asset_selected",
                address=item.address, chain=item.chain,
                asset=asset, asset_basis=asset_basis,
            )
            dust = _dust_for(asset, anchor_chain)

        # Only transactions in the traced asset participate in the value math.
        # Count what that excludes, so an outflow in another asset is reported
        # as exactly that rather than vanishing or masquerading as dust.
        if asset:
            _selfa = item.address.strip().lower()
            other_out = sum(
                1 for tx in txs
                if tx.from_address and tx.from_address.strip().lower() == _selfa
                and (tx.asset or anchor_chain) != asset and tx.amount > 0
            )
            txs = [tx for tx in txs if (tx.asset or anchor_chain) == asset]
        else:
            other_out = 0

        # Resolve an unknown seed from the anchor's own observed inflow: every
        # unit of value seen arriving at the reported address is treated as
        # tainted. Done here rather than before the BFS so it reuses the
        # anchor's already-fetched transaction window instead of costing a
        # second explorer round-trip.
        # Record who funded the anchor, in the asset being traced. Largest
        # first, because that is the order an investigator reads them in.
        if item.hop == 0 and not inbound_sources:
            _self_in = item.address.strip().lower()
            for tx in txs:
                if not tx.to_address or tx.to_address.strip().lower() != _self_in:
                    continue
                if asset and (tx.asset or anchor_chain) != asset:
                    continue
                if not tx.from_address:
                    continue
                inbound_sources.append(
                    InboundSource(
                        address=tx.from_address, chain=item.chain, amount=tx.amount,
                        asset=tx.asset or anchor_chain, tx_hash=tx.tx_hash,
                        timestamp=tx.timestamp,
                    )
                )
            inbound_sources.sort(key=lambda s: s.amount, reverse=True)

        if item.hop == 0 and seed_value is None:
            _self = item.address.strip().lower()
            observed_inflow = sum(
                tx.amount for tx in txs
                if tx.to_address and tx.to_address.strip().lower() == _self
            )
            # A wallet with no observed inflow in the window (e.g. one that has
            # only ever sent) leaves nothing to apportion; fall back to observed
            # outflow so the trace can still follow the money.
            if observed_inflow <= 0:
                observed_inflow = sum(
                    tx.amount for tx in txs
                    if tx.from_address and tx.from_address.strip().lower() == _self
                )
            seed_value = observed_inflow
            item.taint_value = observed_inflow
            logger.info(
                "taint_seed_resolved",
                address=item.address, chain=item.chain,
                seed_value=observed_inflow, seed_basis="observed_inflow",
            )

        wallet_fraction, wallet_first_tainted_at = _estimate_wallet_fraction(
            item.address, txs, item.taint_value, item.first_tainted_at,
        )

        if wallet_fraction < dilution_floor:
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=wallet_fraction, taint_value=item.taint_value,
                terminal_kind=TerminalKind.DUST.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        outgoing = _outgoing_txs(item.address, txs)
        if not outgoing:
            # Tainted funds arrived here and have not moved on (in the fetched
            # window) — this is the most operationally important terminal:
            # money is still sitting at an identified, freezable address. Same
            # real meaning whether this is the anchor itself or a mid-trace
            # dead end — NO_OUTFLOW, not the generic "budget exhausted"
            # NODE_LIMIT this used to (mis)reuse for the root case.
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=wallet_fraction, taint_value=item.taint_value,
                terminal_kind=TerminalKind.NO_OUTFLOW.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))
            continue

        node = TaintedNode(
            address=item.address, chain=item.chain, hop=item.hop,
            taint_fraction=wallet_fraction, taint_value=item.taint_value,
            terminal_kind=None, entity_name=None, entity_jurisdiction=None,
            proof_path=item.proof_path, first_tainted_at=wallet_first_tainted_at,
            still_active=False,
            parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            other_asset_child_count=other_out,
        )
        # Assigned, but NOT reported yet: terminal_kind can still become
        # DILUTED_OUTFLOW once this node's outflows have been examined below,
        # and a listener must never see a node twice or see a non-final one.
        visited[key] = node
        other_asset_branch_count += other_out

        followed = 0
        for tx in outgoing:
            child_value = _apportion(method, tx.amount, wallet_fraction)
            if child_value <= dust:
                # Do NOT silently drop this branch. Haircut dilution legitimately
                # shrinks value at every hop, so a busy wallet can prune dozens of
                # onward transfers — correct forensics, but previously completely
                # invisible, which made the resulting graph look truncated or
                # broken. Count the money instead so the UI can explain itself.
                node.pruned_child_count += 1
                node.pruned_child_value += child_value
                pruned_branch_count += 1
                pruned_branch_value += child_value
                continue
            child_key = (tx.to_address, item.chain)
            if child_key in visited:
                continue
            followed += 1
            heapq.heappush(
                frontier,
                _FrontierItem(
                    sort_key=-child_value, seq=next(counter),
                    address=tx.to_address, chain=item.chain, hop=item.hop + 1,
                    taint_value=child_value,
                    proof_path=[*item.proof_path, tx.tx_hash],
                    first_tainted_at=tx.timestamp,
                    parent_address=item.address, tx_hash=tx.tx_hash, tx_amount=tx.amount,
                ),
            )

        # Had outgoing transfers but followed none of them: a real dead end with
        # a real, stateable reason — not an un-expanded node the UI has to guess
        # about.
        if followed == 0 and node.pruned_child_count > 0:
            node.terminal_kind = TerminalKind.DILUTED_OUTFLOW.value
            node.still_active = True

        if on_event is not None:
            await on_event("node", _node_event(node, len(visited)))
            await on_event("progress", {
                "nodes_settled": len(visited),
                "frontier_size": len(frontier),
                "hop": node.hop,
                "value_following": round(sum(f.taint_value for f in frontier), 8),
                "asset": asset,
            })

    # Budget exhausted with money still untraced — record the largest unresolved
    # branches rather than silently dropping them, while never exceeding the
    # caller's max_nodes (this previously overshot: a requested 40 returned 48).
    if frontier and len(visited) < max_nodes:
        for item in heapq.nsmallest(min(max_nodes - len(visited), len(frontier)), frontier):
            if len(visited) >= max_nodes:
                break
            key = (item.address, item.chain)
            if key in visited:
                continue
            await settle(key, TaintedNode(
                address=item.address, chain=item.chain, hop=item.hop,
                taint_fraction=1.0, taint_value=item.taint_value,
                terminal_kind=TerminalKind.NODE_LIMIT.value,
                entity_name=None, entity_jurisdiction=None,
                proof_path=item.proof_path, first_tainted_at=item.first_tainted_at,
                still_active=True,
                parent_address=item.parent_address, tx_hash=item.tx_hash, tx_amount=item.tx_amount,
                link_basis=item.link_basis, link_confidence=item.link_confidence,
                link_detail=item.link_detail,
            ))

    all_nodes = list(visited.values())

    # Read the finished graph: who is who, and which wallets behave as one
    # operator. This runs AFTER propagation and changes no value: a role is an
    # interpretation of the trace, and the trace has to stand on its own
    # whether or not anyone interprets it.
    annotations = annotate_roles(
        all_nodes,
        anchor_address=anchor_address,
        anchor_chain=anchor_chain,
        asset=asset or anchor_chain,
        inbound_sources=inbound_sources,
        complaint_count=complaint_count,
    )
    cluster_list = apply_clusters(annotations, all_nodes)
    for n in all_nodes:
        ann = annotations.get((n.address.lower(), n.chain))
        if ann is None:
            continue
        n.role = ann.role
        n.role_basis = ann.role_basis
        n.description = ann.description
        n.cluster_id = ann.cluster_id
        n.cluster_label = ann.cluster_label
        n.value_in = ann.value_in
        n.value_out = ann.value_out
        n.value_parked = ann.value_parked

    depth_reached_for_typology = max((n.hop for n in all_nodes), default=0)
    typology_list = detect_typologies(
        all_nodes, inbound_sources, depth_reached_for_typology, anchor_address, anchor_chain,
    )
    path_risk_summary = summarize_path_risk(all_nodes, typology_list)

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

    # Provenance of the data, decided by which explorer actually answered rather
    # than by inspecting addresses. Registry contracts (mixers, bridges, exchange
    # hot wallets) appear in both the live world and the seeded scenarios and are
    # classified as terminals without any fetch at all — testing addresses would
    # mark a genuine live trace that reached Tornado Cash as "seeded", which is
    # the opposite of the honesty this field exists to provide.
    anchor_scenario = scenario_for_address(anchor_address, anchor_chain)
    scenario_key = anchor_scenario.key if anchor_scenario else None
    if sourced_from_fixture and sourced_from_live:
        data_source = "mixed"
    elif sourced_from_fixture:
        data_source = "seeded_scenario"
    else:
        data_source = "live"

    # Why did propagation stop? Stated explicitly so the UI never has to infer
    # "the trace succeeded" from "the trace returned".
    if any(n.terminal_kind == TerminalKind.NODE_LIMIT.value for n in all_nodes):
        termination_reason = "node_budget"
    elif pruned_branch_count > 0 and not frontier:
        termination_reason = "all_branches_dust"
    else:
        termination_reason = "frontier_exhausted"

    return TaintPropagationResult(
        nodes=all_nodes,
        terminals=terminals,
        unattributed_residual=max(0.0, unattributed_residual),
        terminated_at_mixer=terminated_at_mixer,
        reproducible_hash=reproducible_hash,
        depth_reached=max((n.hop for n in all_nodes), default=0),
        termination_reason=termination_reason,
        seed_value=seed_value or 0.0,
        seed_basis=seed_basis,
        pruned_branch_count=pruned_branch_count,
        pruned_branch_value=pruned_branch_value,
        asset=asset or anchor_chain,
        asset_basis=asset_basis,
        other_asset_branch_count=other_asset_branch_count,
        data_source=data_source,
        scenario_key=scenario_key,
        inbound_sources=inbound_sources,
        clusters=[
            {
                "id": c.id, "label": c.label, "basis": c.basis,
                "members": [{"address": a, "chain": ch} for a, ch in c.members],
            }
            for c in cluster_list
        ],
        typologies=[
            {"code": t.code, "label": t.label, "narrative": t.narrative,
             "addresses": [{"address": a, "chain": ch} for a, ch in t.node_keys]}
            for t in typology_list
        ],
        path_risk=path_risk_summary,
    )


# How many transactions to read per address. Bounds both the explorer response
# and the cache entry; a wider window finds more outflows but costs more to
# fetch and parse on every node.
TX_WINDOW = 40

# How many frontier addresses to fetch ahead of the one being processed.
#
# This was 8 and effectively dead: the old implementation skipped any candidate
# already in `tx_cache`, then bailed out entirely on `if len(targets) < 2`. After
# the first batch warmed 8 entries, every later call found fewer than two fresh
# targets and fetched nothing, so the trace fell back to strictly serial
# per-address fetches for the rest of its life. The bail-out is gone and the
# width raised; outbound concurrency is bounded in http_client instead, which is
# the right place for it (the limit that matters is how hard this system leans
# on a free public API, not how wide one BFS frontier is).
_PREFETCH_WIDTH = 12


async def _fetch_for_crosschain(address: str, chain: str) -> list[RawTx]:
    """
    Transactions for `address` on `chain`, for the cross-chain matcher.

    Returns [] rather than raising when no data source exists for that chain —
    POLYGON and BSC have no live explorer here, so a live bridge crossing
    simply finds nothing and the bridge stays an honest terminal. Only a source
    that actually holds the destination chain's transactions can resolve one.
    """
    explorer = _explorer_for(chain, address)
    if explorer is None:
        return []
    try:
        return await _fetch_transactions(explorer, address, chain, TX_WINDOW)
    except ExplorerUnavailableError:
        return []


async def _fetch_transactions(explorer, address: str, chain: str, limit: int) -> list[RawTx]:
    """
    Transactions for one address, via the Redis cache where one applies.

    The fixture explorer is deliberately not cached: it is already a dictionary
    lookup, so a Redis round-trip would make it slower, and a stale entry would
    survive a reseed and quietly contradict the database.
    """
    if isinstance(explorer, FixtureExplorer):
        return await explorer.get_transactions(address, limit=limit)

    cached = await tx_cache_store.get(chain, address, limit)
    if cached is not None:
        return cached

    txs = await explorer.get_transactions(address, limit=limit)
    # Only successful fetches reach here; ExplorerUnavailableError propagates
    # and is never cached. See tx_cache.py for why that distinction matters.
    await tx_cache_store.put(chain, address, txs)
    return txs


async def _prefetch_frontier(
    frontier: list[_FrontierItem],
    visited: dict[tuple[str, str], TaintedNode],
    tx_cache: dict[tuple[str, str], list[RawTx]],
    tx_failures: dict[tuple[str, str], str],
) -> None:
    """
    Warm `tx_cache` with the transaction windows of the next few highest-value
    frontier addresses, concurrently.

    This is a pure latency optimisation and deliberately does NOT change the
    order in which the BFS processes nodes: the caller still pops strictly in
    value order and still re-checks `visited`. Keeping processing sequential is
    what makes a trace reproducible — parallel *expansion* would let whichever
    branch returned first claim the node budget, so the same inputs could
    produce a different graph and a different reproducible_hash.

    A prefetch failure is swallowed: the address is simply fetched again in the
    main loop, where the ExplorerUnavailableError is handled and turned into a
    real EXPLORER_UNAVAILABLE terminal.
    """
    targets: list[_FrontierItem] = []
    for cand in heapq.nsmallest(_PREFETCH_WIDTH, frontier):
        ckey = (cand.address, cand.chain)
        if ckey in visited or ckey in tx_cache or ckey in tx_failures:
            continue
        if any(t.address == cand.address and t.chain == cand.chain for t in targets):
            continue
        if _explorer_for(cand.chain, cand.address) is None:
            continue
        targets.append(cand)
    if not targets:
        return

    async def _fetch(it: _FrontierItem):
        explorer = _explorer_for(it.chain, it.address)
        return await _fetch_transactions(explorer, it.address, it.chain, TX_WINDOW)

    results = await asyncio.gather(*(_fetch(t) for t in targets), return_exceptions=True)
    for target, res in zip(targets, results):
        tkey = (target.address, target.chain)
        if isinstance(res, ExplorerUnavailableError):
            # Recorded, not swallowed. The explorer has already done its own
            # bounded retry inside this call; the main loop repeating it is
            # duplicated wall-clock, not a second opinion. The node still
            # becomes an honest EXPLORER_UNAVAILABLE terminal.
            tx_failures[tkey] = str(res)
        elif isinstance(res, BaseException):
            # An unexpected error (not an explorer outage) is left alone so the
            # main loop can surface it properly rather than mislabelling it.
            continue
        else:
            tx_cache[tkey] = res


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


def _node_event(node: TaintedNode, settled: int) -> dict:
    """
    One settled node, in the same shape `TaintNodeRead` uses.

    Deliberately identical to the final result's node shape so the client feeds
    streamed nodes through exactly the same graph-building code as a completed
    trace, instead of maintaining a second parallel representation that can
    drift. The parent/tx fields ARE the edge — there is no separate edge event.
    """
    return {
        "address": node.address,
        "chain": node.chain,
        "hop": node.hop,
        "taint_fraction": round(node.taint_fraction, 6),
        "tainted_value": round(node.taint_value, 8),
        "terminal_kind": node.terminal_kind,
        "entity_name": node.entity_name,
        "entity_jurisdiction": node.entity_jurisdiction,
        "proof_path": list(node.proof_path),
        "still_active": node.still_active,
        "parent_address": node.parent_address,
        "tx_hash": node.tx_hash,
        "tx_amount": round(node.tx_amount, 8) if node.tx_amount is not None else None,
        "first_tainted_at": node.first_tainted_at.isoformat() if node.first_tainted_at else None,
        "pruned_child_count": node.pruned_child_count,
        "pruned_child_value": round(node.pruned_child_value, 8),
        "other_asset_child_count": node.other_asset_child_count,
        "link_basis": node.link_basis,
        "link_confidence": node.link_confidence,
        "link_detail": node.link_detail,
        # Null during streaming: roles are read from the FINISHED graph, so
        # they arrive with the "done" event. A node cannot know it is the
        # last hop before an exchange until the next hop has been settled.
        "role": node.role,
        "role_basis": node.role_basis,
        "description": node.description,
        "settled_index": settled,
    }


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
