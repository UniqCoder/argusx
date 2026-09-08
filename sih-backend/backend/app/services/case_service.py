"""
app/services/case_service.py — Case Management service with strict state-machine validation.

State Machine transitions (PRD §14.2 / contracts/entities.md):
  new -> investigating, closed
  investigating -> escalated_to_vasp, frozen, closed
  escalated_to_vasp -> frozen, closed, investigating
  frozen -> closed, investigating
  closed -> investigating (re-open)
"""
import uuid
from datetime import datetime, timezone
import logging
from typing import List, Optional, Tuple

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case import Case, CaseWallet
from app.models.wallet import Wallet
from app.schemas.case import CasePatch
from app.schemas.common import CaseStatus

logger = logging.getLogger(__name__)

# Strict state transition graph
VALID_STATUS_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.new: {CaseStatus.investigating, CaseStatus.closed},
    CaseStatus.investigating: {CaseStatus.escalated_to_vasp, CaseStatus.frozen, CaseStatus.closed},
    CaseStatus.escalated_to_vasp: {CaseStatus.frozen, CaseStatus.closed, CaseStatus.investigating},
    CaseStatus.frozen: {CaseStatus.closed, CaseStatus.investigating},
    CaseStatus.closed: {CaseStatus.investigating},
}


def validate_status_transition(current_status_str: str, target_status: CaseStatus) -> None:
    """
    Validate that transitioning from current_status to target_status is permitted.
    Raises HTTPException(422) if invalid.
    """
    try:
        current_status = CaseStatus(current_status_str)
    except ValueError:
        current_status = CaseStatus.new

    if current_status == target_status:
        return

    allowed = VALID_STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        logger.warning(
            "invalid_case_status_transition_attempted",
            extra={"from": current_status.value, "to": target_status.value},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "error": {
                    "code": "INVALID_STATUS_TRANSITION",
                    "message": f"Cannot transition case from '{current_status.value}' to '{target_status.value}'.",
                    "details": {
                        "current_status": current_status.value,
                        "attempted_status": target_status.value,
                        "allowed_transitions": [s.value for s in allowed],
                    },
                }
            },
        )


async def create_case(
    db: AsyncSession,
    assigned_investigator: Optional[str] = None,
    wallet_ids: Optional[List[uuid.UUID]] = None,
    initial_status: CaseStatus = CaseStatus.new,
) -> Case:
    """Create a new case and link initial suspect wallets."""
    case = Case(
        id=uuid.uuid4(),
        status=initial_status.value,
        assigned_investigator=assigned_investigator,
        opened_at=datetime.now(timezone.utc),
        closed_at=None,
    )
    db.add(case)
    await db.flush()

    if wallet_ids:
        for wid in wallet_ids:
            cw = CaseWallet(case_id=case.id, wallet_id=wid)
            db.add(cw)

    await db.commit()
    await db.refresh(case)
    logger.info("case_created", extra={"case_id": str(case.id), "status": case.status})
    return case


async def get_case_by_id(db: AsyncSession, case_id: uuid.UUID) -> Optional[Case]:
    """Retrieve case by UUID."""
    stmt = select(Case).where(Case.id == case_id)
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def get_case_wallets(db: AsyncSession, case_id: uuid.UUID) -> List[Wallet]:
    """Return the wallets explicitly linked to a case."""
    stmt = (
        select(Wallet)
        .join(CaseWallet, CaseWallet.wallet_id == Wallet.id)
        .where(CaseWallet.case_id == case_id)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def list_cases(
    db: AsyncSession,
    status_filter: Optional[CaseStatus] = None,
    page: int = 1,
    page_size: int = 25,
) -> Tuple[List[Case], int]:
    """List paginated cases with optional status filtering."""
    base_query = select(Case)
    count_query = select(func.count(Case.id))

    if status_filter is not None:
        base_query = base_query.where(Case.status == status_filter.value)
        count_query = count_query.where(Case.status == status_filter.value)

    total_res = await db.execute(count_query)
    total = total_res.scalar() or 0

    offset = (page - 1) * page_size
    query = base_query.order_by(Case.opened_at.desc()).offset(offset).limit(page_size)
    res = await db.execute(query)
    cases = list(res.scalars().all())

    return cases, total


async def update_case(
    db: AsyncSession,
    case_id: uuid.UUID,
    patch: CasePatch,
) -> Case:
    """Update case status (validating state transition) or assigned investigator."""
    case = await get_case_by_id(db, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": {
                    "code": "CASE_NOT_FOUND",
                    "message": f"Case with ID '{case_id}' was not found.",
                    "details": {"case_id": str(case_id)},
                }
            },
        )

    if patch.status is not None:
        validate_status_transition(case.status, patch.status)
        case.status = patch.status.value
        if patch.status == CaseStatus.closed:
            case.closed_at = datetime.now(timezone.utc)
        elif case.closed_at is not None:
            case.closed_at = None

    if patch.assigned_investigator is not None:
        case.assigned_investigator = patch.assigned_investigator

    await db.commit()
    await db.refresh(case)
    logger.info("case_updated", extra={"case_id": str(case.id), "status": case.status})
    return case
