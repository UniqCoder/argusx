"""
app/api/v1/routers/alerts.py — Alert registry listing.

Phase 2 implementation.
Polled every 5–10s by the Frontend Alerts & Registry screen.
"""
import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.schemas.alert import AlertRead
from app.schemas.common import ErrorEnvelope, PaginatedResponse
from app.services import alert_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get(
    "",
    response_model=PaginatedResponse[AlertRead],
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
    },
    summary="List alerts (polled every 5–10s by the Alerts screen)",
)
async def list_alerts(
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    resolved: Optional[bool] = Query(default=None, description="Filter: true = resolved, false = open, omit = all"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
) -> PaginatedResponse[AlertRead]:
    """
    List all chokepoint and registry alerts with optional resolution filter and pagination.
    """
    items, total = await alert_service.list_alerts(
        db=db,
        resolved=resolved,
        page=page,
        page_size=page_size,
    )
    return PaginatedResponse[AlertRead](
        items=[AlertRead.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
    )
