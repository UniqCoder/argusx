"""
app/api/v1/routers/correlate.py — Cross-victim correlation (USP 1).

Phase 1 implementation.
Matches exact wallet addresses across complaints without requiring blockchain data.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.schemas.common import ErrorEnvelope
from app.schemas.correlate import CorrelateRequest, CorrelateResponse
from app.services import correlation_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/correlate", tags=["correlation"])


@router.post(
    "",
    response_model=CorrelateResponse,
    responses={
        400: {"model": ErrorEnvelope, "description": "Invalid lookup key"},
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Wallet not found"},
    },
    summary="Cross-victim correlation — how many complaints share this wallet?",
)
async def correlate_wallet(
    body: CorrelateRequest,
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CorrelateResponse:
    """
    Query the database for all complaints associated with a suspect wallet.
    Calculates deterministic correlation score, aggregates geographies, and sums losses.
    """
    result = await correlation_service.correlate_wallet(db, body)

    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "WALLET_NOT_FOUND",
                    "message": "No wallet found for that lookup key.",
                    "details": {
                        "wallet_id": str(body.wallet_id) if body.wallet_id else None,
                        "address": body.address,
                        "chain": body.chain.value if body.chain else None,
                    },
                }
            },
        )

    logger.info(
        "correlation_executed",
        extra={
            "score": result.correlation_score,
            "complaints_count": len(result.linked_complaints),
            "distinct_geographies": result.distinct_geographies,
        },
    )
    return result
