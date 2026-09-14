"""
app/api/v1/routers/scenarios.py — Discovery for the seeded investigation scenarios.

The Trace screen used to carry a hardcoded "load demo case" button wired to a
frontend fixture that bypassed the API entirely — which is why Cross-Victim,
Deposit Watch, Reports and the Evidence Trail all came up empty for it. The
scenarios now live in the database, so the UI asks the server what exists
instead of shipping its own copy.

An unseeded database returns `seeded: false` with the scenario definitions still
listed, so the UI can say "run the reset script" rather than silently showing
cases that will not trace.
"""
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import CurrentUserDep
from app.db.session import get_db
from app.models.engine import Anchor
from app.schemas.common import ErrorEnvelope
from app.schemas.scenario import (
    ScenarioComplaintRead,
    ScenarioListResponse,
    ScenarioRead,
)
from app.services.scenarios.definitions import ALL_SCENARIOS, Scenario

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _chains_for(scenario: Scenario) -> list[str]:
    """Chains in first-appearance order, so ETH -> Polygon -> BSC reads correctly."""
    seen: list[str] = []
    for tx in scenario.txs:
        if tx.chain.value not in seen:
            seen.append(tx.chain.value)
    return seen


@router.get(
    "",
    response_model=ScenarioListResponse,
    responses={401: {"model": ErrorEnvelope, "description": "Unauthorized"}},
    summary="List the seeded investigation scenarios available to trace",
)
async def list_scenarios(
    current_user: CurrentUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ScenarioListResponse:
    rows = await db.execute(
        select(Anchor.source_ref, Anchor.case_id).where(
            Anchor.source_ref.in_([f"scenario:{s.key}" for s in ALL_SCENARIOS])
        )
    )
    case_by_key = {
        ref.split(":", 1)[1]: str(case_id) if case_id else None
        for ref, case_id in rows.all()
    }

    scenarios = [
        ScenarioRead(
            key=s.key,
            title=s.title,
            subtitle=s.subtitle,
            typology=s.typology,
            headline=s.headline,
            demonstrates=list(s.demonstrates),
            anchor_address=s.anchor_address,
            anchor_chain=s.anchor_chain,
            asset=s.asset,
            chains=_chains_for(s),
            victim_amount_inr=s.victim_amount_inr,
            complaint_count=len(s.complaints),
            transaction_count=len(s.txs),
            complaints=[
                ScenarioComplaintRead(
                    ncrp_ref=c.ncrp_ref,
                    source_platform=c.source_platform,
                    state=c.state,
                    district=c.district,
                    fraud_typology=c.fraud_typology,
                    amount_lost_inr=c.amount_lost_inr,
                )
                for c in s.complaints
            ],
            case_id=case_by_key.get(s.key),
        )
        for s in ALL_SCENARIOS
    ]

    return ScenarioListResponse(
        seeded=any(s.case_id for s in scenarios),
        scenarios=scenarios,
    )
