"""
app/workers/tasks/alerts.py — Async Celery tasks for alert notification and processing.

Triggered on /check-wallet hold/block decisions, executing off the API request path.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.session import AsyncSessionLocal
from app.models.alert import Alert
from app.models.wallet import Wallet
from app.models.case import Case
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


async def _process_alert_async(
    chain: str,
    address: str,
    risk_score: float,
    action: str,
    case_ref: Optional[str] = None,
    amount: Optional[float] = None,
) -> str:
    """Async worker logic to record alert in PostgreSQL."""
    async with AsyncSessionLocal() as session:
        # 1. Upsert wallet record
        stmt = insert(Wallet).values(
            id=uuid.uuid4(),
            address=address,
            chain=chain.upper(),
            risk_score=risk_score,
            last_seen=datetime.now(timezone.utc),
        ).on_conflict_do_update(
            index_elements=["address", "chain"],
            set_={
                "risk_score": risk_score,
                "last_seen": datetime.now(timezone.utc),
            }
        ).returning(Wallet.id)

        res = await session.execute(stmt)
        wallet_id = res.scalar_one()

        # 2. Look up case by assigned or open case if case_ref is provided
        case_id = None
        if case_ref:
            case_stmt = select(Case.id).limit(1)
            case_res = await session.execute(case_stmt)
            case_id = case_res.scalar_one_or_none()

        # 3. Create Alert entry
        alert = Alert(
            id=uuid.uuid4(),
            wallet_id=wallet_id,
            case_id=case_id,
            triggered_by="check_wallet_hook",
            action=action,
            created_at=datetime.now(timezone.utc),
        )
        session.add(alert)
        await session.commit()
        await session.refresh(alert)

        logger.info(
            "chokepoint_alert_recorded",
            extra={
                "alert_id": str(alert.id),
                "wallet_id": str(wallet_id),
                "address": address,
                "chain": chain,
                "action": action,
                "amount": amount,
            },
        )
        return str(alert.id)


@celery_app.task(name="app.workers.tasks.alerts.notify_alert_task", bind=True, max_retries=3)
def notify_alert_task(
    self,
    chain: str,
    address: str,
    risk_score: float,
    action: str,
    case_ref: Optional[str] = None,
    amount: Optional[float] = None,
) -> str:
    """
    Celery task dispatched on hold/block decisions from /check-wallet.
    Runs asynchronously off the API response path.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            task = asyncio.ensure_future(
                _process_alert_async(chain, address, risk_score, action, case_ref, amount)
            )
            return "queued"
        else:
            return loop.run_until_complete(
                _process_alert_async(chain, address, risk_score, action, case_ref, amount)
            )
    except Exception as exc:
        try:
            # Create a new event loop if necessary
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            result = new_loop.run_until_complete(
                _process_alert_async(chain, address, risk_score, action, case_ref, amount)
            )
            new_loop.close()
            return result
        except Exception as retry_exc:
            logger.error("notify_alert_task_failed", extra={"error": str(retry_exc)})
            raise self.retry(exc=retry_exc, countdown=5)
