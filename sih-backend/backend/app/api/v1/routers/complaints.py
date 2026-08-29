"""
app/api/v1/routers/complaints.py — Complaint ingestion, listing, and detail view with LLM entity extraction.

Phase 1 + Phase 6 implementation (USP 1 & USP 3).
Routes:
  - POST /api/v1/complaints: Ingest complaint, returns 201
  - GET  /api/v1/complaints: List complaints with pagination and filtering
  - GET  /api/v1/complaints/{id}: Complaint detail enriched with read-only local LLM/spaCy extracted entities
"""
import logging
from typing import Annotated, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.schemas.common import ErrorEnvelope, PaginatedResponse
from app.schemas.complaint import ComplaintCreate, ComplaintDetailRead, ComplaintRead
from app.services import complaint_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/complaints", tags=["complaints"])


@router.post(
    "",
    response_model=ComplaintRead,
    status_code=status.HTTP_201_CREATED,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
    summary="Ingest a new complaint",
)
async def create_complaint(
    body: ComplaintCreate,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ComplaintRead:
    """
    Ingest a new victim complaint.
    Narrative text is stored locally and never transmitted to external APIs.
    """
    complaint = await complaint_service.create_complaint(db, body)
    logger.info("complaint_created", extra={"id": str(complaint.id), "ncrp_ref": complaint.ncrp_ref})
    return ComplaintRead.model_validate(complaint)


@router.get(
    "",
    response_model=PaginatedResponse[ComplaintRead],
    responses={401: {"model": ErrorEnvelope}},
    summary="List complaints",
)
async def list_complaints(
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    state: Optional[str] = Query(default=None),
    fraud_typology: Optional[str] = Query(default=None),
) -> PaginatedResponse[ComplaintRead]:
    """
    Retrieve a paginated list of complaints with optional state and typology filters.
    """
    items, total = await complaint_service.list_complaints(
        db=db,
        page=page,
        page_size=page_size,
        state=state,
        fraud_typology=fraud_typology,
    )
    return PaginatedResponse[ComplaintRead](
        items=[ComplaintRead.model_validate(c) for c in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{id}",
    response_model=ComplaintDetailRead,
    responses={
        401: {"model": ErrorEnvelope},
        403: {"model": ErrorEnvelope},
        404: {"model": ErrorEnvelope},
    },
    summary="Get complaint details with local LLM extracted entities",
)
async def get_complaint(
    id: Annotated[UUID, Path(description="Complaint UUID")],
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ComplaintDetailRead:
    """
    Get full complaint details enriched with read-only entities extracted by local air-gapped Llama-3.2-3B / spaCy.
    """
    complaint_detail = await complaint_service.get_complaint_with_entities(db, id)
    if complaint_detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "COMPLAINT_NOT_FOUND",
                    "message": f"Complaint with ID '{id}' was not found.",
                    "details": {"complaint_id": str(id)},
                }
            },
        )
    return complaint_detail
