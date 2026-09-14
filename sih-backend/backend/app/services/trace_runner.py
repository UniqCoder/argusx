"""
app/services/trace_runner.py — Persisting a completed trace.

Extracted from the POST /engine/trace handler so the synchronous endpoint and
the streaming job endpoint write *identical* rows. Two copies of this would
have drifted within a week, and the thing that would drift is the forensic
record: the Trace row's honesty fields, the per-node taint, the decision's
basis, and the hash-chained ledger entries.

The layering rule (routers -> services -> models) is why this lives here rather
than in the router.
"""
from __future__ import annotations

import datetime as _dt
from decimal import Decimal

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.engine import ledger as ledger_engine
from app.engine.decision import decide
from app.engine.taint import TaintPropagationResult
from app.models.engine import Anchor, Decision, TaintNode, Trace
from app.schemas.engine import TraceRequest

logger = structlog.get_logger(__name__)


async def persist_trace(
    db: AsyncSession,
    anchor: Anchor,
    body: TraceRequest,
    result: TaintPropagationResult,
    actor: str,
) -> tuple[Trace, Decision]:
    """Write the trace, its nodes, the decision it justifies, and the ledger entries."""
    trace = Trace(
        anchor_id=anchor.id,
        method=body.method.value,
        dilution_floor=body.dilution_floor,
        max_hops=body.max_hops,
        max_nodes=body.max_nodes,
        node_count=len(result.nodes),
        reproducible_hash=result.reproducible_hash,
        # Persisted so the GET endpoint, the PDF report and the dashboard graph
        # all describe this trace with the same caveats — max_hops is the
        # request, depth_reached is the outcome.
        depth_reached=result.depth_reached,
        termination_reason=result.termination_reason,
        seed_value=Decimal(str(round(result.seed_value, 8))),
        seed_basis=result.seed_basis,
        pruned_branch_count=result.pruned_branch_count,
        pruned_branch_value=Decimal(str(round(result.pruned_branch_value, 8))),
        asset=result.asset,
        asset_basis=result.asset_basis,
        other_asset_branch_count=result.other_asset_branch_count,
        data_source=result.data_source,
        scenario_key=result.scenario_key,
        inbound_sources=[
            {
                "address": src.address, "chain": src.chain, "amount": str(round(src.amount, 8)),
                "asset": src.asset, "tx_hash": src.tx_hash,
                "timestamp": src.timestamp.isoformat() if src.timestamp else None,
            }
            for src in result.inbound_sources
        ],
        clusters=result.clusters,
        typologies=result.typologies,
        path_risk=result.path_risk,
    )
    db.add(trace)
    await db.flush()

    victim_amount = anchor.victim_amount_inr
    for node in result.nodes:
        tainted_inr = (
            Decimal(str(victim_amount)) * Decimal(str(round(node.taint_fraction, 6)))
            if victim_amount is not None
            else None
        )
        db.add(
            TaintNode(
                trace_id=trace.id,
                address=node.address,
                chain=node.chain,
                hop=node.hop,
                taint_fraction=node.taint_fraction,
                tainted_value=node.taint_value,
                tainted_inr=tainted_inr,
                terminal_kind=node.terminal_kind,
                entity_name=node.entity_name,
                entity_jurisdiction=node.entity_jurisdiction,
                proof_path=node.proof_path,
                first_tainted_at=node.first_tainted_at,
                parent_address=node.parent_address,
                tx_hash=node.tx_hash,
                tx_amount=node.tx_amount,
                pruned_child_count=node.pruned_child_count,
                pruned_child_value=node.pruned_child_value,
                other_asset_child_count=node.other_asset_child_count,
                role=node.role,
                role_basis=node.role_basis,
                description=node.description,
                cluster_id=node.cluster_id,
                cluster_label=node.cluster_label,
                value_in=node.value_in,
                value_out=node.value_out,
                value_parked=node.value_parked,
                link_basis=node.link_basis,
                link_confidence=node.link_confidence,
                link_detail=node.link_detail,
            )
        )

    trace.completed_at = _dt.datetime.now(_dt.timezone.utc)

    # Feed the strongest VASP terminal (if any) to the decision engine.
    vasp_terminals = [n for n in result.terminals if n.terminal_kind == "VASP"]
    best_terminal = max(vasp_terminals, key=lambda n: n.taint_value, default=None)
    if best_terminal is None and result.terminals:
        best_terminal = max(result.terminals, key=lambda n: n.taint_value)

    decision_result = decide(
        anchor_id=anchor.id,
        anchor_attestation_class=anchor.attestation_class,
        trace_id=trace.id,
        terminal=best_terminal,
    )
    decision = Decision(
        case_id=anchor.case_id,
        address=anchor.address,
        chain=anchor.chain,
        action=decision_result.action.value,
        basis_anchor_id=decision_result.basis_anchor_id,
        basis_trace_id=decision_result.basis_trace_id,
        ml_contributed=decision_result.ml_contributed,
        reasoning=decision_result.reasoning,
        expires_at=decision_result.expires_at,
    )
    db.add(decision)
    await db.commit()
    await db.refresh(trace)
    await db.refresh(decision)

    await ledger_engine.append_entry(
        db,
        event_type="trace_completed",
        payload={
            "trace_id": str(trace.id),
            "anchor_id": str(anchor.id),
            "node_count": len(result.nodes),
            "reproducible_hash": result.reproducible_hash,
            # Recorded in the tamper-evident ledger too, so an exported evidence
            # trail cannot omit that a trace ran on seeded data.
            "data_source": result.data_source,
            "scenario_key": result.scenario_key,
        },
        actor=actor,
        case_id=anchor.case_id,
    )
    await ledger_engine.append_entry(
        db,
        event_type="decision_issued",
        payload={
            "decision_id": str(decision.id),
            "action": decision.action,
            "reasoning": decision.reasoning,
        },
        actor=actor,
        case_id=anchor.case_id,
    )

    logger.info(
        "trace_persisted",
        trace_id=str(trace.id),
        anchor_id=str(anchor.id),
        node_count=len(result.nodes),
        decision=decision.action,
        data_source=result.data_source,
    )
    return trace, decision
