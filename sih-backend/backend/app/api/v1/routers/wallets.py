"""
app/api/v1/routers/wallets.py — Wallet tracing and risk score endpoints.

Routes:
  - GET /api/v1/wallets/{address}/trace: multi-hop trace to nearest VASP (Phase 3)
  - GET /api/v1/wallets/{address}/risk:  ML risk score + SHAP evidence (Phase 4)
"""
import structlog
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep, InvestigatorOrAdminDep
from app.db.session import get_db
from app.schemas.check_wallet import (
    CheckWalletRequest,
    CheckWalletResponse,
    DepositDecisionRequest,
    DepositDecisionResponse,
)
from app.schemas.common import Chain, ErrorEnvelope
from app.schemas.wallet import RiskResponse, TraceResponse
from app.services import registry_service, risk_service, tracing_service

logger = structlog.get_logger(__name__)

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
        address=address,
        chain=chain.value,
        hops_count=result.hops_count,
        nearest_vasp=result.nearest_vasp,
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


@router.post(
    "/deposit-check",
    response_model=CheckWalletResponse,
    status_code=status.HTTP_200_OK,
    responses={
        401: {"model": ErrorEnvelope, "description": "Unauthorized"},
        403: {"model": ErrorEnvelope, "description": "Forbidden"},
        422: {"model": ErrorEnvelope, "description": "Validation error"},
    },
    summary="Investigator-facing deposit chokepoint check (Deposit Watch page)",
)
async def deposit_check(
    body: CheckWalletRequest,
    current_user: InvestigatorOrAdminDep,
) -> CheckWalletResponse:
    """
    Same Redis risk-registry lookup as the external VASP-facing /check-wallet
    hot path, gated by investigator JWT auth instead of a VASP API key so the
    Deposit Watch dashboard page can run the real check without exposing the
    VASP API key to the browser.
    """
    if body.chain not in (Chain.BTC, Chain.ETH, Chain.TRON):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "UNSUPPORTED_CHAIN",
                    "message": f"Blockchain network '{body.chain.value}' is not supported for risk check. Supported networks: BTC, ETH, TRON.",
                    "details": {"chain": body.chain.value},
                }
            },
        )

    redis_client = registry_service.get_redis_client()
    score, action, case_ref, reason, tier = await registry_service.check_wallet_hot_path(
        redis_client=redis_client,
        chain=body.chain.value,
        address=body.address,
        amount=body.amount,
    )
    return CheckWalletResponse(
        risk_score=score, action=action, case_ref=case_ref, reason=reason, risk_tier=tier
    )


@router.post(
    "/deposit-decision",
    response_model=DepositDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    responses={401: {"model": ErrorEnvelope}, 403: {"model": ErrorEnvelope}},
    summary="Record what an investigator did with a Deposit Watch verdict",
)
async def record_deposit_decision(
    body: DepositDecisionRequest,
    current_user: InvestigatorOrAdminDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DepositDecisionResponse:
    """
    A compliance override used to leave no trace anywhere: "Override / Allow"
    and "Allow Transaction" only flipped local component state. This appends
    an entry to the same tamper-evident evidence ledger a trace decision
    writes to, so an allow on a held/blocked wallet is an auditable act with
    an actor and a timestamp, not a silent client-side click.
    """
    from app.engine import ledger as ledger_engine

    await ledger_engine.append_entry(
        db,
        event_type="deposit_decision",
        payload={
            "address": body.address,
            "chain": body.chain.value,
            "risk_score": body.risk_score,
            "registry_action": body.action.value,
            "decision": body.decision,
            "case_ref": body.case_ref,
            "note": body.note,
        },
        actor=current_user.sub,
        # Real case linkage, when the investigator had an active case — not
        # the opaque `case_ref` label, which isn't guaranteed to be a case
        # in this database. Without this, every flagged/allowed deposit was
        # written to the ledger but permanently invisible in any case's
        # Evidence Trail (which is filtered by case_id), even though the
        # write itself succeeded — "recorded to the evidence ledger" was
        # true but unverifiable by the investigator.
        case_id=body.case_id,
    )
    return DepositDecisionResponse(recorded=True)
