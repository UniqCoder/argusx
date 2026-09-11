"""
app/engine/decision.py — Layer 5: the three-tier decision engine.

The load-bearing constraint of the whole engine (ARGUS-ENGINE-V2.md §3 and
§Layer 5): a `block` decision cannot be produced by ML alone. It requires a
Class-A anchor (legally attested / sovereign) connected by a Layer-1 taint
path reaching an attributed terminal with sufficient taint fraction.

This is enforced THREE times, deliberately redundant:
  1. Here, in code — decide() cannot construct a block Decision without both.
  2. In the ORM/DB — Decision.__table_args__ ck_block_requires_anchor CHECK
     constraint (app/models/engine.py) rejects it even on a direct insert.
  3. In tests — test_ml_alone_can_never_block (app/tests/test_engine_decision.py).
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from app.engine.taint import TaintedNode
from app.schemas.engine import AttestationClass, DecisionAction

BLOCK_MIN_TAINT_FRACTION = 0.10
HOLD_MIN_ML_SCORE = 0.70
HOLD_EXPIRES_AFTER = timedelta(hours=4)


class StructuralGuardError(Exception):
    """Raised if calling code attempts to force a block without qualifying evidence."""


@dataclass
class DecisionResult:
    action: DecisionAction
    basis_anchor_id: Optional[UUID]
    basis_trace_id: Optional[UUID]
    ml_contributed: bool
    reasoning: str
    expires_at: Optional[datetime]


def decide(
    *,
    anchor_id: Optional[UUID],
    anchor_attestation_class: Optional[str],
    trace_id: Optional[UUID],
    terminal: Optional[TaintedNode],
    ml_score: Optional[float] = None,
) -> DecisionResult:
    """
    anchor_attestation_class / terminal come from Layers 0/1 (deterministic).
    ml_score comes from Layer 4 (triage) — it can only ever raise a
    hold_for_review; see the assertion at the bottom of this function, which
    is the actual code a judge can be shown for "ML alone can never block".
    """
    has_class_a_anchor = anchor_id is not None and anchor_attestation_class == AttestationClass.A.value
    has_qualifying_terminal = (
        terminal is not None
        and terminal.terminal_kind in ("VASP",)
        and terminal.taint_fraction >= BLOCK_MIN_TAINT_FRACTION
    )

    if has_class_a_anchor and trace_id is not None and has_qualifying_terminal:
        result = DecisionResult(
            action=DecisionAction.block,
            basis_anchor_id=anchor_id,
            basis_trace_id=trace_id,
            ml_contributed=ml_score is not None,
            reasoning=(
                f"Class-A anchor {anchor_id} + taint trace {trace_id} reached "
                f"{terminal.entity_name} with taint_fraction={terminal.taint_fraction:.3f} "
                f"(>= {BLOCK_MIN_TAINT_FRACTION})."
            ),
            expires_at=None,
        )
        _assert_block_has_deterministic_basis(result)
        return result

    if ml_score is not None and ml_score >= HOLD_MIN_ML_SCORE:
        return DecisionResult(
            action=DecisionAction.hold_for_review,
            basis_anchor_id=anchor_id,
            basis_trace_id=trace_id,
            ml_contributed=True,
            reasoning=(
                f"ML triage score {ml_score:.3f} >= {HOLD_MIN_ML_SCORE}. Soft hold only — "
                "ML cannot produce a block (see ARGUS-ENGINE-V2.md §3)."
            ),
            expires_at=datetime.now(timezone.utc) + HOLD_EXPIRES_AFTER,
        )

    if anchor_id is not None and terminal is not None and terminal.terminal_kind is not None:
        return DecisionResult(
            action=DecisionAction.hold_for_review,
            basis_anchor_id=anchor_id,
            basis_trace_id=trace_id,
            ml_contributed=False,
            reasoning=(
                f"Anchor present but evidence insufficient for a block "
                f"(class={anchor_attestation_class}, terminal={terminal.terminal_kind}, "
                f"taint_fraction={terminal.taint_fraction:.3f}). Routed for manual review."
            ),
            expires_at=datetime.now(timezone.utc) + HOLD_EXPIRES_AFTER,
        )

    return DecisionResult(
        action=DecisionAction.monitor,
        basis_anchor_id=anchor_id,
        basis_trace_id=trace_id,
        ml_contributed=ml_score is not None,
        reasoning="No qualifying evidence yet — logged for monitoring only.",
        expires_at=None,
    )


def _assert_block_has_deterministic_basis(result: DecisionResult) -> None:
    """
    The structural guarantee, as code. If this ever fires, it is a bug in
    decide() above, not a policy violation to be waived — that's the point.
    """
    if result.action == DecisionAction.block and (
        result.basis_anchor_id is None or result.basis_trace_id is None
    ):
        raise StructuralGuardError(
            "A block decision was about to be constructed without both a "
            "basis_anchor_id and a basis_trace_id. ML triage alone can never "
            "produce a block — see ARGUS-ENGINE-V2.md §3."
        )
