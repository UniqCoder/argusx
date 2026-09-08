"""
app/api/v1/routers/check_wallet.py — VASP deposit chokepoint (USP 2).

This router is mounted at root /check-wallet (NOT under /api/v1/) and uses
X-API-Key authentication (apiKeyAuth) — used exclusively by external VASPs.

Hot path: reads Redis only (risk:{chain}:{address}).
Never touches Postgres or Neo4j synchronously.
Target: p95 < 200ms.
"""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis

from app.api.v1.deps import VaspKeyDep
from app.schemas.check_wallet import CheckWalletRequest, CheckWalletResponse
from app.schemas.common import AlertAction, Chain, ErrorEnvelope
from app.services import registry_service
from app.workers.tasks.alerts import notify_alert_task

logger = logging.getLogger(__name__)

router = APIRouter(tags=["vasp"])


def get_redis() -> Redis:
    """Dependency injection for Redis client."""
    return registry_service.get_redis_client()


@router.post(
    "/check-wallet",
    response_model=CheckWalletResponse,
    responses={
        401: {"model": ErrorEnvelope, "description": "Invalid or missing API key"},
        422: {"model": ErrorEnvelope, "description": "Validation error"},
    },
    summary="Real-time risk check for VASP deposit chokepoint (p95 < 200ms)",
)
async def check_wallet(
    body: CheckWalletRequest,
    _api_key: VaspKeyDep,
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> CheckWalletResponse:
    """
    Real-time chokepoint evaluated by VASPs on incoming deposits before crediting funds.
    Queries the Redis risk registry only (<5ms hot path).
    Dispatches alert processing asynchronously via Celery on hold/block decisions.
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

    score, action, case_ref = await registry_service.check_wallet_hot_path(
        redis_client=redis_client,
        chain=body.chain.value,
        address=body.address,
        amount=body.amount,
    )

    # If action is hold or block, dispatch asynchronous alert notification off the response path
    if action in (AlertAction.hold, AlertAction.block):
        try:
            notify_alert_task.apply_async(
                kwargs={
                    "chain": body.chain.value,
                    "address": body.address,
                    "risk_score": score,
                    "action": action.value,
                    "case_ref": case_ref,
                    "amount": body.amount,
                },
                retry=False,
            )
        except Exception as e:
            # Never block or fail the hot path if celery broker dispatch has an issue
            logger.warning("celery_alert_dispatch_failed", extra={"error": str(e)})

    logger.info(
        "check_wallet_executed",
        extra={
            "address": body.address,
            "chain": body.chain.value,
            "score": score,
            "action": action.value,
            "case_ref": case_ref,
        },
    )

    return CheckWalletResponse(
        risk_score=score,
        action=action,
        case_ref=case_ref,
    )
