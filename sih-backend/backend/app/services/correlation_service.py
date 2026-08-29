"""
app/services/correlation_service.py — Cross-Victim Correlation Engine (USP 1).

Mines the complaint database to find shared wallets across complaints without
requiring external blockchain data.

Deterministic scoring logic:
  - 0 complaints: 0.0
  - 1 complaint: 0.10 (isolated report, base risk)
  - 2 complaints: 0.50 + 0.05 * min(distinct_geographies, 2)  (0.55 - 0.60)
  - 3 complaints: 0.70 + 0.05 * min(distinct_geographies, 3)  (0.75 - 0.85)
  - 4+ complaints: min(1.0, 0.85 + 0.02 * count + 0.02 * distinct_geographies)

Rules:
  - Exact match only for Phase 1.
  - Strict router -> service -> models layering.
"""
from typing import Optional
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint, ComplaintWallet
from app.models.wallet import Wallet
from app.schemas.complaint import ComplaintRead
from app.schemas.correlate import CorrelateRequest, CorrelateResponse


def calculate_correlation_score(complaint_count: int, distinct_geographies: int) -> float:
    """
    Deterministic correlation scoring function based on report volume and geographic spread.
    Returns float in range [0.0, 1.0].
    """
    if complaint_count <= 0:
        return 0.0
    if complaint_count == 1:
        return 0.10
    if complaint_count == 2:
        return round(0.50 + 0.05 * min(distinct_geographies, 2), 2)
    if complaint_count == 3:
        return round(0.70 + 0.05 * min(distinct_geographies, 3), 2)
    
    score = 0.85 + (0.02 * complaint_count) + (0.02 * distinct_geographies)
    return round(min(1.0, score), 2)


async def correlate_wallet(
    db: AsyncSession,
    request: CorrelateRequest,
) -> Optional[CorrelateResponse]:
    """
    Execute cross-victim correlation for a given wallet (by wallet_id or address+chain).
    Returns None if wallet is not found.
    """
    # 1. Resolve wallet
    if request.wallet_id is not None:
        wallet_stmt = select(Wallet).where(Wallet.id == request.wallet_id)
    else:
        wallet_stmt = select(Wallet).where(
            Wallet.address == request.address,
            Wallet.chain == request.chain.value if request.chain else None,
        )

    wallet_res = await db.execute(wallet_stmt)
    wallet = wallet_res.scalar_one_or_none()

    if wallet is None:
        return None

    # 2. Query linked complaints through complaint_wallets junction
    stmt = (
        select(Complaint)
        .join(ComplaintWallet, ComplaintWallet.complaint_id == Complaint.id)
        .where(ComplaintWallet.wallet_id == wallet.id)
        .order_by(Complaint.filed_at.desc())
    )
    result = await db.execute(stmt)
    complaints = result.scalars().all()

    # 3. Compute metrics
    linked_complaints = [ComplaintRead.model_validate(c) for c in complaints]
    distinct_geographies = len({c.state for c in complaints if c.state})
    total_amount = round(sum(float(c.amount_lost or 0.0) for c in complaints), 2)
    correlation_score = calculate_correlation_score(len(linked_complaints), distinct_geographies)

    return CorrelateResponse(
        correlation_score=correlation_score,
        linked_complaints=linked_complaints,
        distinct_geographies=distinct_geographies,
        total_amount=total_amount,
    )
