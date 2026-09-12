"""
app/api/v1/routers/engine.py — ARGUS v2 provenance engine endpoints.

Purely additive: new prefix (/api/v1/anchors, /api/v1/engine/*), new schemas,
new service module (app/engine/*). No existing route's request/response shape
changes, so the existing frontend API client is unaffected.

Mutating endpoints (anchor registration, running a trace) require
investigator/admin — a compliance_viewer (read-only per PRD §5) cannot create
ground-truth anchors or trigger a freeze-adjacent decision.
"""
import logging
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep, InvestigatorOrAdminDep
from app.db.session import get_db
from app.engine import anchors as anchor_engine
from app.engine import ledger as ledger_engine
from app.engine.anchors import DuplicateAnchorError
from app.engine.decision import decide
from app.engine.taint import propagate_taint
from app.models.engine import Decision, TaintNode, Trace
from app.schemas.common import ErrorEnvelope
from app.schemas.engine import (
    AnchorCreate,
    AnchorRead,
    DecisionRead,
    LedgerVerifyResponse,
    TaintNodeRead,
    TraceRequest,
    TraceResult,
)

logger = logging.getLogger(__name__)

anchors_router = APIRouter(prefix="/anchors", tags=["engine"])
engine_router = APIRouter(prefix="/engine", tags=["engine"])


# ── Layer 0 — Anchors ───────────────────────────────────────────────────────────

@anchors_router.post(
    "",
    response_model=AnchorRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope, "description": "Duplicate anchor"},
        422: {"model": ErrorEnvelope},
    },
    summary="Register a ground-truth anchor (Layer 0) — FIR/NCRP complaint or sovereign designation",
)
async def create_anchor(
    body: AnchorCreate,
    current_user: InvestigatorOrAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AnchorRead:
    """
    Nothing in the engine treats an address as tainted without one of these.
    See ARGUS-ENGINE-V2.md §Layer 0. system_generated is always False here —
    anchors are externally attested only (anti-feedback-loop guard).
    """
    try:
        anchor = await anchor_engine.create_anchor(db, body)
    except DuplicateAnchorError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": {
                    "code": "DUPLICATE_ANCHOR",
                    "message": str(exc),
                    "details": {"address": body.address, "chain": body.chain.value, "source_ref": body.source_ref},
                }
            },
        ) from exc

    await ledger_engine.append_entry(
        db,
        event_type="anchor_registered",
        payload={
            "anchor_id": str(anchor.id),
            "address": anchor.address,
            "chain": anchor.chain,
            "attestation_class": anchor.attestation_class,
            "source_ref": anchor.source_ref,
        },
        actor=current_user.sub,
    )
    logger.info("anchor_registered", extra={"anchor_id": str(anchor.id), "source_ref": anchor.source_ref})
    return AnchorRead.model_validate(anchor)


# ── Layer 1 — Trace ─────────────────────────────────────────────────────────────

@engine_router.post(
    "/trace",
    response_model=TraceResult,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope, "description": "Anchor not found"},
    },
    summary="Run taint propagation from an anchor (Layer 1) and issue a decision (Layer 5)",
)
async def run_trace(
    body: TraceRequest,
    current_user: InvestigatorOrAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TraceResult:
    """
    Synchronous for this slice (bounded max_nodes/max_hops keep it fast enough
    for the demo path — ARGUS-ENGINE-V2.md Stage 1). A Celery-async variant is
    listed as later-stage work once trace volume requires it; the contract
    here (poll GET /engine/trace/{id}) is unchanged either way.
    """
    anchor = await anchor_engine.get_anchor(db, body.anchor_id)
    if anchor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "ANCHOR_NOT_FOUND",
                    "message": f"Anchor '{body.anchor_id}' was not found.",
                    "details": {"anchor_id": str(body.anchor_id)},
                }
            },
        )

    result = await propagate_taint(
        anchor_address=anchor.address,
        anchor_chain=anchor.chain,
        anchor_taint_value=1.0,
        method=body.method,
        max_hops=body.max_hops,
        max_nodes=body.max_nodes,
        dilution_floor=float(body.dilution_floor),
    )

    trace = Trace(
        anchor_id=anchor.id,
        method=body.method.value,
        dilution_floor=body.dilution_floor,
        max_hops=body.max_hops,
        max_nodes=body.max_nodes,
        node_count=len(result.nodes),
        reproducible_hash=result.reproducible_hash,
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
            )
        )

    import datetime as _dt
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
            "trace_id": str(trace.id), "anchor_id": str(anchor.id),
            "node_count": len(result.nodes), "reproducible_hash": result.reproducible_hash,
        },
        actor=current_user.sub,
    )
    await ledger_engine.append_entry(
        db,
        event_type="decision_issued",
        payload={
            "decision_id": str(decision.id), "action": decision.action,
            "reasoning": decision.reasoning,
        },
        actor=current_user.sub,
    )

    logger.info(
        "trace_completed",
        extra={
            "trace_id": str(trace.id), "anchor_id": str(anchor.id),
            "node_count": len(result.nodes), "decision": decision.action,
        },
    )

    return _build_trace_result(anchor, trace, result.nodes, result.terminals,
                                result.unattributed_residual, result.terminated_at_mixer)


@engine_router.get(
    "/trace/{trace_id}",
    response_model=TraceResult,
    responses={404: {"model": ErrorEnvelope}},
    summary="Fetch a persisted trace",
)
async def get_trace(
    trace_id: UUID,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TraceResult:
    trace = (await db.execute(select(Trace).where(Trace.id == trace_id))).scalar_one_or_none()
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TRACE_NOT_FOUND", "message": f"Trace '{trace_id}' not found.", "details": {}}},
        )
    anchor = await anchor_engine.get_anchor(db, trace.anchor_id)
    node_rows = (await db.execute(select(TaintNode).where(TaintNode.trace_id == trace_id))).scalars().all()

    nodes = [
        _taint_node_from_row(row) for row in node_rows
    ]
    terminals = [n for n in nodes if n.terminal_kind is not None]
    unattributed = sum(
        float(n.tainted_value) for n in nodes
        if n.terminal_kind not in ("VASP", "MIXER_BOUNDARY") and n.terminal_kind is not None
    )
    mixer_total = sum(float(n.tainted_value) for n in nodes if n.terminal_kind == "MIXER_BOUNDARY")

    return TraceResult(
        trace_id=trace.id,
        anchor=AnchorRead.model_validate(anchor),
        method=trace.method,
        dilution_floor=trace.dilution_floor,
        max_hops=trace.max_hops,
        node_count=trace.node_count or len(nodes),
        nodes=nodes,
        terminals=terminals,
        unattributed_residual=Decimal(str(unattributed)),
        terminated_at_mixer=Decimal(str(mixer_total)),
        reproducible_hash=trace.reproducible_hash,
        completed_at=trace.completed_at,
    )


@engine_router.get(
    "/trace/{trace_id}/proof",
    responses={404: {"model": ErrorEnvelope}},
    summary="Verifiable proof bundle: parameters + reproducible hash + tx-hash paths",
)
async def get_trace_proof(
    trace_id: UUID,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    trace = (await db.execute(select(Trace).where(Trace.id == trace_id))).scalar_one_or_none()
    if trace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "TRACE_NOT_FOUND", "message": f"Trace '{trace_id}' not found.", "details": {}}},
        )
    node_rows = (await db.execute(select(TaintNode).where(TaintNode.trace_id == trace_id))).scalars().all()
    return {
        "trace_id": str(trace.id),
        "method": trace.method,
        "max_hops": trace.max_hops,
        "max_nodes": trace.max_nodes,
        "dilution_floor": str(trace.dilution_floor),
        "reproducible_hash": trace.reproducible_hash,
        "proof_paths": {
            row.address: row.proof_path for row in node_rows if row.proof_path
        },
    }


# ── Layer 5 — Ledger ─────────────────────────────────────────────────────────────

@engine_router.get(
    "/decisions/{decision_id}",
    response_model=DecisionRead,
    responses={404: {"model": ErrorEnvelope}},
    summary="Fetch a decision (freeze/hold/monitor) with its basis anchor and trace",
)
async def get_decision(
    decision_id: UUID,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DecisionRead:
    decision = (await db.execute(select(Decision).where(Decision.id == decision_id))).scalar_one_or_none()
    if decision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {"code": "DECISION_NOT_FOUND", "message": f"Decision '{decision_id}' not found.", "details": {}}},
        )
    return DecisionRead.model_validate(decision)


@engine_router.get(
    "/ledger/verify",
    response_model=LedgerVerifyResponse,
    summary="Recompute the hash chain and confirm the evidence ledger's integrity",
)
async def verify_ledger(
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    case_id: Annotated[Optional[UUID], Query(description="Restrict to one case's chain")] = None,
) -> LedgerVerifyResponse:
    return await ledger_engine.verify_chain(db, case_id=case_id)


def _taint_node_from_row(row: TaintNode) -> TaintNodeRead:
    return TaintNodeRead(
        address=row.address,
        chain=row.chain,
        hop=row.hop,
        taint_fraction=row.taint_fraction,
        tainted_value=row.tainted_value,
        tainted_inr=row.tainted_inr,
        terminal_kind=row.terminal_kind,
        entity_name=row.entity_name,
        entity_jurisdiction=row.entity_jurisdiction,
        proof_path=row.proof_path or [],
        still_active=row.terminal_kind not in ("MIXER_BOUNDARY",),
        parent_address=row.parent_address,
        tx_hash=row.tx_hash,
        tx_amount=row.tx_amount,
        first_tainted_at=row.first_tainted_at,
    )


def _build_trace_result(anchor, trace, engine_nodes, engine_terminals, unattributed, mixer_total) -> TraceResult:
    nodes = [
        TaintNodeRead(
            address=n.address, chain=n.chain, hop=n.hop,
            taint_fraction=Decimal(str(round(n.taint_fraction, 6))),
            tainted_value=Decimal(str(round(n.taint_value, 8))),
            tainted_inr=(
                Decimal(str(anchor.victim_amount_inr)) * Decimal(str(round(n.taint_fraction, 6)))
                if anchor.victim_amount_inr is not None else None
            ),
            terminal_kind=n.terminal_kind, entity_name=n.entity_name,
            entity_jurisdiction=n.entity_jurisdiction, proof_path=n.proof_path,
            still_active=n.still_active,
            parent_address=n.parent_address, tx_hash=n.tx_hash,
            tx_amount=(Decimal(str(round(n.tx_amount, 8))) if n.tx_amount is not None else None),
            first_tainted_at=n.first_tainted_at,
        )
        for n in engine_nodes
    ]
    terminals = [n for n in nodes if n.terminal_kind is not None]
    return TraceResult(
        trace_id=trace.id,
        anchor=AnchorRead.model_validate(anchor),
        method=trace.method,
        dilution_floor=trace.dilution_floor,
        max_hops=trace.max_hops,
        node_count=len(nodes),
        nodes=nodes,
        terminals=terminals,
        unattributed_residual=Decimal(str(round(unattributed, 8))),
        terminated_at_mixer=Decimal(str(round(mixer_total, 8))),
        reproducible_hash=trace.reproducible_hash,
        completed_at=trace.completed_at,
    )
