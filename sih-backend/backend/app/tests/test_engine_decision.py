"""
app/tests/test_engine_decision.py — Layer 5 structural guarantee tests.

This is the file to show a judge who asks "will your model freeze an
innocent person's money?" (ARGUS-ENGINE-V2.md §20, Q1). It proves — in code,
not policy prose — that a block decision requires a Class-A anchor plus a
taint trace, and that ML alone can never produce one, at two independent
layers: the Python decision function, and the database CHECK constraint.
"""
import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.decision import BLOCK_MIN_TAINT_FRACTION, decide
from app.engine.taint import TaintedNode
from app.models.engine import Decision
from app.schemas.engine import DecisionAction

ANCHOR_ID = uuid.uuid4()
TRACE_ID = uuid.uuid4()


def _vasp_terminal(taint_fraction: float) -> TaintedNode:
    return TaintedNode(
        address="VASP_ADDR", chain="BTC", hop=3, taint_fraction=taint_fraction,
        taint_value=0.9, terminal_kind="VASP", entity_name="Binance",
        entity_jurisdiction="Cayman Islands", proof_path=["tx1", "tx2"],
        first_tainted_at=None, still_active=True,
    )


def test_ml_alone_can_never_block():
    """The headline test. A high ML score with NO anchor must never block."""
    result = decide(
        anchor_id=None, anchor_attestation_class=None, trace_id=None,
        terminal=None, ml_score=0.99,
    )
    assert result.action != DecisionAction.block
    assert result.action == DecisionAction.hold_for_review


def test_class_c_anchor_cannot_block_even_with_strong_terminal():
    """A mere investigator hypothesis (class C) is not sufficient evidence to block."""
    result = decide(
        anchor_id=ANCHOR_ID, anchor_attestation_class="C", trace_id=TRACE_ID,
        terminal=_vasp_terminal(0.95), ml_score=0.99,
    )
    assert result.action != DecisionAction.block


def test_class_a_anchor_with_weak_terminal_holds_not_blocks():
    """Below the taint-fraction floor, even a Class-A anchor only earns a hold."""
    weak_terminal = _vasp_terminal(BLOCK_MIN_TAINT_FRACTION / 2)
    result = decide(
        anchor_id=ANCHOR_ID, anchor_attestation_class="A", trace_id=TRACE_ID,
        terminal=weak_terminal, ml_score=None,
    )
    assert result.action == DecisionAction.hold_for_review


def test_class_a_anchor_plus_taint_path_can_block():
    """The one path that CAN produce a block: Class-A anchor + trace + qualifying terminal."""
    result = decide(
        anchor_id=ANCHOR_ID, anchor_attestation_class="A", trace_id=TRACE_ID,
        terminal=_vasp_terminal(0.9), ml_score=None,
    )
    assert result.action == DecisionAction.block
    assert result.basis_anchor_id == ANCHOR_ID
    assert result.basis_trace_id == TRACE_ID


def test_class_a_anchor_without_a_trace_cannot_block():
    """An anchor alone, with no taint trace run yet, is not enough."""
    result = decide(
        anchor_id=ANCHOR_ID, anchor_attestation_class="A", trace_id=None,
        terminal=_vasp_terminal(0.95), ml_score=None,
    )
    assert result.action != DecisionAction.block


def test_no_evidence_at_all_is_monitor_only():
    result = decide(anchor_id=None, anchor_attestation_class=None, trace_id=None, terminal=None)
    assert result.action == DecisionAction.monitor


# ── Database-level guarantee (survives even a service-layer bug) ───────────────

@pytest.mark.asyncio
async def test_db_rejects_block_decision_without_anchor_and_trace(db_session: AsyncSession):
    """
    Even a direct, hand-crafted INSERT that bypasses decide() entirely is
    rejected by the ck_block_requires_anchor CHECK constraint.
    """
    bad_decision = Decision(
        address="SOME_ADDRESS",
        chain="BTC",
        action="block",
        basis_anchor_id=None,
        basis_trace_id=None,
        reasoning="attempting to force a block with no evidence",
    )
    db_session.add(bad_decision)
    with pytest.raises(IntegrityError):
        await db_session.commit()
