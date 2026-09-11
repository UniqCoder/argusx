"""
app/tests/test_engine_taint.py — Layer 1 (taint propagation) correctness tests.

Per ARGUS-ENGINE-V2.md §18.1, taint propagation is arithmetic, not a model —
so these are conservation/determinism/termination invariant tests, not
accuracy tests. Explorer calls are monkeypatched to canned data (no live
network dependency), unlike the existing test_trace.py which intentionally
hits live mainnet explorers for the v1 tracing_service.
"""
from datetime import datetime, timezone

import pytest

from app.engine import taint as taint_module
from app.engine.taint import (
    TaintedNode,
    _apportion,
    _compute_reproducible_hash,
    _estimate_wallet_fraction,
    propagate_taint,
)
from app.schemas.common import Chain
from app.schemas.engine import TaintMethod
from app.services.explorers.base import RawTx

ANCHOR = "ANCHOR1"
MID = "MID1"
PEEL = "PEEL1"
VASP_ADDR = "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ"  # curated Binance BTC address

_NOW = datetime(2026, 9, 11, tzinfo=timezone.utc)

_CANNED: dict[str, list[RawTx]] = {
    ANCHOR: [
        RawTx(tx_hash="tx1", from_address=ANCHOR, to_address=MID, amount=1.0, chain=Chain.BTC, timestamp=_NOW),
    ],
    MID: [
        RawTx(tx_hash="tx1", from_address=ANCHOR, to_address=MID, amount=1.0, chain=Chain.BTC, timestamp=_NOW),
        RawTx(tx_hash="tx2", from_address=MID, to_address=VASP_ADDR, amount=0.9, chain=Chain.BTC, timestamp=_NOW),
        RawTx(tx_hash="tx3", from_address=MID, to_address=PEEL, amount=0.1, chain=Chain.BTC, timestamp=_NOW),
    ],
    PEEL: [
        RawTx(tx_hash="tx3", from_address=MID, to_address=PEEL, amount=0.1, chain=Chain.BTC, timestamp=_NOW),
    ],
}


async def _fake_get_transactions(address: str, limit: int = 25) -> list[RawTx]:
    return _CANNED.get(address, [])


@pytest.fixture(autouse=True)
def _patch_btc_explorer(monkeypatch):
    monkeypatch.setattr(taint_module._btc, "get_transactions", _fake_get_transactions)


# ── Pure-function unit tests ────────────────────────────────────────────────────

def test_apportion_haircut_scales_by_fraction():
    assert _apportion(TaintMethod.haircut, tx_amount=1.0, wallet_fraction=0.3) == pytest.approx(0.3)


def test_apportion_poison_ignores_fraction_but_requires_nonzero():
    assert _apportion(TaintMethod.poison, tx_amount=1.0, wallet_fraction=0.01) == pytest.approx(1.0)
    assert _apportion(TaintMethod.poison, tx_amount=1.0, wallet_fraction=0.0) == pytest.approx(0.0)


def test_estimate_wallet_fraction_defaults_to_full_taint_with_no_observed_inflow():
    """
    No incoming tx observed in the fetched window -> conservative 100% taint,
    never a guessed-lower number we can't support (see module docstring).
    """
    fraction, _ = _estimate_wallet_fraction("X", [], incoming_taint_value=5.0, fallback_first_tainted_at=None)
    assert fraction == 1.0


def test_estimate_wallet_fraction_dilutes_with_other_inflow():
    txs = [
        RawTx(tx_hash="a", from_address="P1", to_address="X", amount=1.0, chain=Chain.BTC, timestamp=_NOW),
        RawTx(tx_hash="b", from_address="P2", to_address="X", amount=3.0, chain=Chain.BTC, timestamp=_NOW),
    ]
    # 1.0 of the 4.0 total inflow is tainted -> 25%
    fraction, _ = _estimate_wallet_fraction("X", txs, incoming_taint_value=1.0, fallback_first_tainted_at=None)
    assert fraction == pytest.approx(0.25)


def test_reproducible_hash_is_deterministic():
    nodes = [
        TaintedNode(
            address="A", chain="BTC", hop=0, taint_fraction=1.0, taint_value=1.0,
            terminal_kind=None, entity_name=None, entity_jurisdiction=None,
            proof_path=[], first_tainted_at=None, still_active=False,
        ),
    ]
    h1 = _compute_reproducible_hash("A", "BTC", TaintMethod.haircut, 5, 20, 0.005, nodes)
    h2 = _compute_reproducible_hash("A", "BTC", TaintMethod.haircut, 5, 20, 0.005, nodes)
    assert h1 == h2
    assert len(h1) == 64  # sha256 hex digest


def test_reproducible_hash_changes_with_params():
    nodes = []
    h1 = _compute_reproducible_hash("A", "BTC", TaintMethod.haircut, 5, 20, 0.005, nodes)
    h2 = _compute_reproducible_hash("A", "BTC", TaintMethod.haircut, 6, 20, 0.005, nodes)
    assert h1 != h2


# ── Integration: full BFS over canned data ──────────────────────────────────────

@pytest.mark.asyncio
async def test_propagate_taint_conservation_and_terminals():
    """
    ANCHOR1 --1.0--> MID1 --0.9--> VASP (Binance, terminal)
                          \\--0.1--> PEEL1 (no further outflow, terminal)

    Value conservation: sum(terminal taint values) <= anchor taint value
    (equality here since there's no dust loss in this scenario).
    """
    result = await propagate_taint(
        anchor_address=ANCHOR, anchor_chain="BTC", anchor_taint_value=1.0,
        method=TaintMethod.haircut, max_hops=5, max_nodes=20, dilution_floor=0.001,
    )

    total_terminal_value = sum(n.taint_value for n in result.terminals)
    assert total_terminal_value <= 1.0 + 1e-9

    vasp_terminals = [n for n in result.terminals if n.terminal_kind == "VASP"]
    assert len(vasp_terminals) == 1
    assert vasp_terminals[0].address == VASP_ADDR
    assert vasp_terminals[0].entity_name == "Binance"
    assert vasp_terminals[0].taint_value == pytest.approx(0.9)
    assert vasp_terminals[0].proof_path == ["tx1", "tx2"]

    peel_terminals = [n for n in result.terminals if n.address == PEEL]
    assert len(peel_terminals) == 1
    assert peel_terminals[0].terminal_kind == "NO_OUTFLOW"
    assert peel_terminals[0].still_active is True  # money is still sitting there — freezable
    assert peel_terminals[0].taint_value == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_propagate_taint_is_deterministic_given_same_inputs():
    r1 = await propagate_taint(
        anchor_address=ANCHOR, anchor_chain="BTC", anchor_taint_value=1.0,
        method=TaintMethod.haircut, max_hops=5, max_nodes=20, dilution_floor=0.001,
    )
    r2 = await propagate_taint(
        anchor_address=ANCHOR, anchor_chain="BTC", anchor_taint_value=1.0,
        method=TaintMethod.haircut, max_hops=5, max_nodes=20, dilution_floor=0.001,
    )
    assert r1.reproducible_hash == r2.reproducible_hash


@pytest.mark.asyncio
async def test_propagate_taint_respects_max_hops():
    """max_hops=0 must terminate the anchor itself at DEPTH_LIMIT — no expansion at all."""
    result = await propagate_taint(
        anchor_address=ANCHOR, anchor_chain="BTC", anchor_taint_value=1.0,
        method=TaintMethod.haircut, max_hops=0, max_nodes=20, dilution_floor=0.001,
    )
    assert len(result.nodes) == 1
    assert result.nodes[0].terminal_kind == "DEPTH_LIMIT"
