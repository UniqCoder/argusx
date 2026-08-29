"""
app/api/v1/routers/cases.py — Case Management & Forensic PDF Report Router.

Routes:
  - POST /api/v1/cases: create case
  - GET  /api/v1/cases: list cases with status filter & pagination
  - GET  /api/v1/cases/{id}: get case details
  - PATCH /api/v1/cases/{id}: update status / assign investigator (state machine enforced)
  - GET  /api/v1/cases/{id}/report: stream official forensic PDF report
"""
import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.schemas.case import CaseCreate, CasePatch, CaseRead
from app.schemas.common import CaseStatus, ErrorEnvelope, PaginatedResponse
from app.services import audit_service, case_service, report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cases", tags=["cases"])


@router.post(
    "",
    response_model=CaseRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        422: {"model": ErrorEnvelope, "description": "Validation error"},
    },
    summary="Create a new investigation case",
)
async def create_case(
    payload: CaseCreate,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CaseRead:
    """Create a new case file and link initial suspect wallet IDs."""
    case = await case_service.create_case(
        db=db,
        assigned_investigator=payload.assigned_investigator,
        wallet_ids=payload.wallet_ids,
        initial_status=payload.initial_status,
    )
    return CaseRead.model_validate(case)


@router.get(
    "",
    response_model=PaginatedResponse[CaseRead],
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
    },
    summary="List cases with optional status filter",
)
async def list_cases(
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[Optional[CaseStatus], Query(description="Filter by case status")] = None,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 25,
) -> PaginatedResponse[CaseRead]:
    """Retrieve paginated list of cases."""
    cases, total = await case_service.list_cases(
        db=db,
        status_filter=status,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[CaseRead.model_validate(c) for c in cases],
    )


@router.get(
    "/{id}",
    response_model=CaseRead,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Case not found"},
    },
    summary="Get case details by ID",
)
async def get_case(
    id: Annotated[UUID, Path(description="Case UUID")],
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CaseRead:
    """Retrieve a single case by its UUID."""
    case = await case_service.get_case_by_id(db, id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "CASE_NOT_FOUND",
                    "message": f"Case with ID '{id}' was not found.",
                    "details": {"case_id": str(id)},
                }
            },
        )
    await audit_service.record_audit_log(
        db=db,
        actor=getattr(current_user, "sub", "investigator"),
        action="view_case",
        entity="case",
        entity_id=case.id,
    )
    return CaseRead.model_validate(case)


@router.patch(
    "/{id}",
    response_model=CaseRead,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Case not found"},
        422: {"model": ErrorEnvelope, "description": "Invalid state machine transition"},
    },
    summary="Update case status or assigned investigator",
)
async def update_case(
    id: Annotated[UUID, Path(description="Case UUID")],
    patch: CasePatch,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CaseRead:
    """
    Update case attributes. Status transitions are strictly validated against the state machine.
    """
    updated_case = await case_service.update_case(db, id, patch)
    await audit_service.record_audit_log(
        db=db,
        actor=getattr(current_user, "sub", "investigator"),
        action="update_case_status",
        entity="case",
        entity_id=updated_case.id,
    )
    return CaseRead.model_validate(updated_case)


@router.get(
    "/{id}/report",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "content": {"application/pdf": {}},
            "description": "Binary PDF forensic report stream",
        },
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Case not found"},
    },
    summary="Download forensic PDF case report",
)
async def get_case_report(
    id: Annotated[UUID, Path(description="Case UUID to generate report for")],
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """
    Generate and stream an official forensic PDF report aggregating
    ML risk scores, SHAP evidence, multi-hop trace paths, and NCRP complaints.
    """
    pdf_bytes = await report_service.generate_case_pdf_report(db, id)
    filename = f"unigraph_case_{str(id)[:8]}.pdf"

    await audit_service.record_audit_log(
        db=db,
        actor=getattr(current_user, "sub", "investigator"),
        action="export_pdf_report",
        entity="case",
        entity_id=id,
    )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "application/pdf",
        },
    )
