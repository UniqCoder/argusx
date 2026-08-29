"""
app/workers/tasks/registry_refresh.py — Async Risk Registry Refresh Celery Task (Phase 4).

Computes ML risk score and populates the Redis risk registry (risk:{chain}:{address})
so /check-wallet hot-path lookups remain purely in Redis.
"""
import asyncio
import logging
from typing import Optional

from app.core.config import get_settings
from app.db.session import async_session_factory
from app.schemas.common import Chain
from app.services import registry_service, risk_service
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


async def _refresh_wallet_risk_async(address: str, chain: str, case_ref: Optional[str] = None) -> dict:
    """Async helper evaluating risk and setting Redis registry key."""
    chain_enum = Chain(chain.upper())
    
    async with async_session_factory() as db:
        risk_res = await risk_service.evaluate_wallet_risk(
            db=db,
            address=address,
            chain=chain_enum,
        )

    # Populate Redis risk registry key: risk:{chain}:{address}
    await registry_service.set_risk_entry(
        chain=chain_enum.value,
        address=address,
        score=risk_res.risk_score,
        tier=risk_res.risk_tier.value,
        case_ref=case_ref,
    )

    logger.info(
        "registry_risk_refreshed",
        extra={
            "address": address,
            "chain": chain,
            "score": risk_res.risk_score,
            "tier": risk_res.risk_tier.value,
        },
    )

    return {
        "address": address,
        "chain": chain,
        "risk_score": risk_res.risk_score,
        "risk_tier": risk_res.risk_tier.value,
        "status": "refreshed",
    }


@celery_app.task(name="app.workers.tasks.registry_refresh.refresh_wallet_risk_task", bind=True, max_retries=2)
def refresh_wallet_risk_task(self, address: str, chain: str, case_ref: Optional[str] = None) -> dict:
    """
    Celery task to asynchronously compute ML risk and update the Redis risk registry.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_refresh_wallet_risk_async(address, chain, case_ref))
            return {"status": "queued"}
        else:
            return loop.run_until_complete(_refresh_wallet_risk_async(address, chain, case_ref))
    except Exception:
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        result = new_loop.run_until_complete(_refresh_wallet_risk_async(address, chain, case_ref))
        new_loop.close()
        return result
