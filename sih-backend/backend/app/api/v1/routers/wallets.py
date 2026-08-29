"""
app/api/v1/routers/wallets.py — Wallet tracing and risk score endpoints.

Routes:
  - GET /api/v1/wallets/{address}/trace: multi-hop trace to nearest VASP (Phase 3)
  - GET /api/v1/wallets/{address}/risk:  ML risk score + SHAP evidence (Phase 4)
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.schemas.common import Chain, ErrorEnvelope
from app.schemas.wallet import RiskResponse, TraceResponse
from app.services import risk_service, tracing_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallets", tags=["wallets"])


@router.get(
    "/{address}/trace",
    response_model=TraceResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Wallet not found"},
    },
    summary="Trace a wallet's transaction path to nearest VASP",
)
async def trace_wallet(
    address: Annotated[str, Path(description="Blockchain wallet address to trace", example="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")],
    chain: Annotated[Chain, Query(description="Target blockchain network", example="BTC")],
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TraceResponse:
    """
    Trace on-chain transaction hops from the target suspect address to the nearest
    identified VASP / exchange deposit chokepoint.
    """
    result = await tracing_service.trace_wallet_to_vasp(
        db=db,
        address=address,
        chain=chain,
    )
    logger.info(
        "wallet_traced",
        extra={
            "address": address,
            "chain": chain.value,
            "hops_count": result.hops_count,
            "nearest_vasp": result.nearest_vasp,
        },
    )
    return result


@router.get(
    "/{address}/risk",
    response_model=RiskResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        404: {"model": ErrorEnvelope, "description": "Wallet not found"},
    },
    summary="Get ML risk score and SHAP evidence for a wallet",
)
async def get_wallet_risk(
    address: Annotated[str, Path(description="Wallet address to evaluate", example="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh")],
    chain: Annotated[Chain, Query(description="Blockchain network", example="BTC")],
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RiskResponse:
    """
    Compute real-time ML risk scoring and SHAP explainability evidence for a wallet address.
    """
    result = await risk_service.evaluate_wallet_risk(
        db=db,
        address=address,
        chain=chain,
    )
    return result
