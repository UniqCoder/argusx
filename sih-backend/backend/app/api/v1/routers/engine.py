"""
app/api/v1/routers/engine.py — ARGUS v2 provenance engine endpoints.

Purely additive: new prefix (/api/v1/anchors, /api/v1/engine/*), new schemas,
new service module (app/engine/*). No existing route's request/response shape
changes, so the existing frontend API client is unaffected.

Mutating endpoints (anchor registration, running a trace) require
investigator/admin — a compliance_viewer (read-only per PRD §5) cannot create
ground-truth anchors or trigger a freeze-adjacent decision.
"""
import asyncio
import json
import logging
from decimal import Decimal
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep, InvestigatorOrAdminDep
from app.db.session import AsyncSessionLocal, get_db
from app.engine import anchors as anchor_engine
from app.engine import ledger as ledger_engine
from app.engine.anchors import DuplicateAnchorError
from app.engine.taint import propagate_taint
from app.models.engine import Anchor, Decision, TaintNode, Trace
from app.schemas.common import ErrorEnvelope
from app.services import complaint_service, trace_jobs
from app.services.trace_runner import persist_trace
from app.schemas.engine import (
    AnchorCreate,
    AnchorRead,
    ClusterRead,
    DecisionRead,
    InboundSourceRead,
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
        case_id=anchor.case_id,
    )
    logger.info("anchor_registered", extra={"anchor_id": str(anchor.id), "source_ref": anchor.source_ref})
    return AnchorRead.model_validate(anchor)


async def _complaint_count_for(db: AsyncSession, address: str, chain: str) -> int:
    """How many complaints name this address — the basis for PRIMARY_SUSPECT.

    Thin wrapper: the actual query now lives in complaint_service, shared
    with app/services/risk_service.py's corroboration bonus so the engine's
    role assignment and the risk score's evidence are counting the same
    thing the same way.
    """
    return await complaint_service.complaint_count_for(db, address, chain)


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

    # The tainted seed, in the chain's native unit. This was hardcoded to 1.0
    # — i.e. every trace silently assumed "exactly 1.0 ETH/BTC/TRX was stolen"
    # regardless of the actual complaint, and every taint_fraction downstream
    # was arithmetic on that invented number. Now: use the amount the caller
    # states if there is one, otherwise pass None so the engine seeds from the
    # anchor address's real observed inflow. Which of the two was used is
    # reported back on the result as `seed_basis`, so it is never ambiguous.
    complaint_count = await _complaint_count_for(db, anchor.address, anchor.chain)
    result = await propagate_taint(
        anchor_address=anchor.address,
        anchor_chain=anchor.chain,
        anchor_taint_value=float(body.seed_value) if body.seed_value is not None else None,
        method=body.method,
        max_hops=body.max_hops,
        max_nodes=body.max_nodes,
        dilution_floor=float(body.dilution_floor),
        complaint_count=complaint_count,
    )

    trace, _decision = await persist_trace(db, anchor, body, result, actor=current_user.sub)

    return _build_trace_result(anchor, trace, result.nodes, result.terminals,
                                result.unattributed_residual, result.terminated_at_mixer,
                                result.inbound_sources, result.clusters,
                                result.typologies, result.path_risk)


# ── Layer 1 (streaming) — watch a trace as it runs ────────────────────────────
#
# Same engine, same ordering, same persisted rows as POST /engine/trace. The
# only difference is that nodes are reported as they are settled instead of all
# at once at the end, so the graph draws from the first hop rather than after
# the last one. See app/services/trace_jobs.py for the single-process caveat.


async def _run_trace_job(job_id: str, anchor_id: UUID, body: TraceRequest, actor: str) -> None:
    """The background half of a streaming trace. Owns its own DB session."""
    job = trace_jobs.get_job(job_id)
    if job is None:
        return

    async def emit(event_type: str, data: dict) -> None:
        job.append(event_type, data)
        # Hand control back to the event loop so a subscriber can actually send
        # what was just appended. Without this the engine's awaits are all on
        # network I/O and a fast (seeded) trace would arrive as one burst at the
        # end — technically streamed, visibly not.
        await asyncio.sleep(0)

    try:
        async with AsyncSessionLocal() as db:
            anchor = await anchor_engine.get_anchor(db, anchor_id)
            if anchor is None:
                job.fail("ANCHOR_NOT_FOUND", f"Anchor '{anchor_id}' was not found.")
                return

            await emit("started", {
                "anchor_id": str(anchor.id),
                "address": anchor.address,
                "chain": anchor.chain,
                "max_hops": body.max_hops,
                "max_nodes": body.max_nodes,
            })

            complaint_count = await _complaint_count_for(db, anchor.address, anchor.chain)
            result = await propagate_taint(
                anchor_address=anchor.address,
                anchor_chain=anchor.chain,
                anchor_taint_value=float(body.seed_value) if body.seed_value is not None else None,
                method=body.method,
                max_hops=body.max_hops,
                max_nodes=body.max_nodes,
                dilution_floor=float(body.dilution_floor),
                on_event=emit,
                complaint_count=complaint_count,
            )

            trace, _decision = await persist_trace(db, anchor, body, result, actor=actor)
            payload = _build_trace_result(
                anchor, trace, result.nodes, result.terminals,
                result.unattributed_residual, result.terminated_at_mixer,
                result.inbound_sources, result.clusters,
                result.typologies, result.path_risk,
            )
            job.finish(json.loads(payload.model_dump_json()))
    except Exception as exc:  # noqa: BLE001 — the job must report, never vanish
        logger.exception("trace_job_failed", extra={"job_id": job_id})
        job.fail("TRACE_FAILED", str(exc))


@engine_router.post(
    "/trace/jobs",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope, "description": "Anchor not found"},
    },
    summary="Start a trace and stream its nodes as the engine settles them",
)
async def start_trace_job(
    body: TraceRequest,
    current_user: InvestigatorOrAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # Validate the anchor before accepting the job, so a bad anchor_id is a 404
    # on this request rather than an error event on a stream nobody is watching
    # yet.
    anchor = await anchor_engine.get_anchor(db, body.anchor_id)
    if anchor is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {
                "code": "ANCHOR_NOT_FOUND",
                "message": f"Anchor '{body.anchor_id}' was not found.",
                "details": {"anchor_id": str(body.anchor_id)},
            }},
        )

    job = trace_jobs.create_job()
    asyncio.create_task(_run_trace_job(job.id, body.anchor_id, body, current_user.sub))
    return {
        "job_id": job.id,
        "status": job.status,
        "events_url": f"/api/v1/engine/trace/jobs/{job.id}/events",
        "snapshot_url": f"/api/v1/engine/trace/jobs/{job.id}",
    }


@engine_router.get(
    "/trace/jobs/{job_id}/events",
    responses={404: {"model": ErrorEnvelope}},
    summary="Server-sent event stream of a running trace",
)
async def stream_trace_job(
    job_id: str,
    current_user: InvestigatorOrAdminDep,
):
    job = trace_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {
                "code": "JOB_NOT_FOUND",
                "message": f"Trace job '{job_id}' was not found or has expired.",
                "details": {"job_id": job_id},
            }},
        )

    async def event_stream():
        async for event in trace_jobs.subscribe(job):
            yield f"event: {event['type']}\ndata: {json.dumps(event['data'])}\n\n"
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Nginx and friends buffer by default, which would hold the whole
            # stream until the trace finished — the exact behaviour this
            # endpoint exists to avoid.
            "X-Accel-Buffering": "no",
        },
    )


@engine_router.get(
    "/trace/jobs/{job_id}",
    responses={404: {"model": ErrorEnvelope}},
    summary="Snapshot of a trace job, for clients that cannot hold a stream open",
)
async def get_trace_job(job_id: str, current_user: InvestigatorOrAdminDep) -> dict:
    job = trace_jobs.get_job(job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": {
                "code": "JOB_NOT_FOUND",
                "message": f"Trace job '{job_id}' was not found or has expired.",
                "details": {"job_id": job_id},
            }},
        )
    return trace_jobs.snapshot(job)


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
        # Read back from the persisted row so a re-fetched trace carries the
        # same caveats the original run reported. Traces written before
        # migration 0005 have no recorded accounting: depth_reached is still
        # genuinely recoverable from the stored hops, the rest are reported as
        # "unrecorded" rather than back-filled with invented values.
        depth_reached=(
            trace.depth_reached
            if trace.depth_reached is not None
            else max((n.hop for n in nodes), default=0)
        ),
        termination_reason=trace.termination_reason or "unrecorded",
        seed_value=Decimal(str(trace.seed_value or 0)),
        seed_basis=trace.seed_basis or "unrecorded",
        pruned_branch_count=trace.pruned_branch_count or 0,
        pruned_branch_value=Decimal(str(trace.pruned_branch_value or 0)),
        asset=trace.asset or "unrecorded",
        asset_basis=trace.asset_basis or "unrecorded",
        other_asset_branch_count=trace.other_asset_branch_count or 0,
        data_source=trace.data_source or "live",
        scenario_key=trace.scenario_key,
        inbound_sources=[
            InboundSourceRead.model_validate(s) for s in (trace.inbound_sources or [])
        ],
        clusters=[ClusterRead.model_validate(c) for c in (trace.clusters or [])],
        typologies=trace.typologies or [],
        path_risk=trace.path_risk or {},
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
        pruned_child_count=row.pruned_child_count or 0,
        pruned_child_value=Decimal(str(row.pruned_child_value or 0)),
        other_asset_child_count=row.other_asset_child_count or 0,
        role=row.role,
        role_basis=row.role_basis,
        description=row.description,
        cluster_id=row.cluster_id,
        cluster_label=row.cluster_label,
        value_in=Decimal(str(row.value_in or 0)),
        value_out=Decimal(str(row.value_out or 0)),
        value_parked=Decimal(str(row.value_parked or 0)),
        link_basis=row.link_basis or "ON_CHAIN",
        link_confidence=float(row.link_confidence) if row.link_confidence is not None else None,
        link_detail=row.link_detail,
    )


def _build_trace_result(anchor, trace, engine_nodes, engine_terminals, unattributed, mixer_total,
                         inbound_sources=(), clusters=(), typologies=(), path_risk=None) -> TraceResult:
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
            pruned_child_count=n.pruned_child_count or 0,
            pruned_child_value=Decimal(str(n.pruned_child_value or 0)),
            other_asset_child_count=n.other_asset_child_count or 0,
            role=n.role,
            role_basis=n.role_basis,
            description=n.description,
            cluster_id=n.cluster_id,
            cluster_label=n.cluster_label,
            value_in=Decimal(str(round(n.value_in, 8))),
            value_out=Decimal(str(round(n.value_out, 8))),
            value_parked=Decimal(str(round(n.value_parked, 8))),
            link_basis=n.link_basis,
            link_confidence=n.link_confidence,
            link_detail=n.link_detail,
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
        inbound_sources=[
            InboundSourceRead(
                address=src.address, chain=src.chain, amount=Decimal(str(round(src.amount, 8))),
                asset=src.asset, tx_hash=src.tx_hash, timestamp=src.timestamp,
            )
            for src in inbound_sources
        ],
        clusters=[ClusterRead.model_validate(c) for c in clusters],
        typologies=list(typologies),
        path_risk=path_risk or {},
        # Traces created before migration 0005 have no recorded accounting.
        # Fall back to values derivable from the stored nodes rather than
        # inventing any: depth_reached is genuinely recoverable from the hops.
        depth_reached=(
            trace.depth_reached
            if trace.depth_reached is not None
            else max((n.hop for n in engine_nodes), default=0)
        ),
        termination_reason=trace.termination_reason or "unrecorded",
        seed_value=Decimal(str(trace.seed_value or 0)),
        seed_basis=trace.seed_basis or "unrecorded",
        pruned_branch_count=trace.pruned_branch_count or 0,
        pruned_branch_value=Decimal(str(trace.pruned_branch_value or 0)),
        asset=trace.asset or "unrecorded",
        asset_basis=trace.asset_basis or "unrecorded",
        other_asset_branch_count=trace.other_asset_branch_count or 0,
        data_source=trace.data_source or "live",
        scenario_key=trace.scenario_key,
    )
