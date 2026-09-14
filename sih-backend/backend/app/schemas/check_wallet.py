"""app/schemas/check_wallet.py — VASP deposit chokepoint schemas."""
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import AlertAction, Chain, RiskTier


class CheckWalletRequest(BaseModel):
    address: str
    chain: Chain
    amount: float = Field(..., gt=0)


class CheckWalletResponse(BaseModel):
    risk_score: float = Field(..., ge=0.0, le=1.0)
    action: AlertAction
    case_ref: Optional[str] = None
    # The recorded basis for a flagged entry, when one exists (the sanctions
    # seed and the seeded scenarios both carry one). Deposit Watch shows this
    # instead of asking an investigator to trust a bare number.
    reason: Optional[str] = None
    # The SAME risk_tier Risk Intelligence shows for this wallet — the
    # frontend must color-code off this, never re-derive its own score
    # thresholds. None for an unflagged/never-scored address.
    risk_tier: Optional[RiskTier] = None


class DepositDecisionRequest(BaseModel):
    """Records what an investigator did with a Deposit Watch verdict."""
    address: str
    chain: Chain
    risk_score: float = Field(..., ge=0.0, le=1.0)
    action: AlertAction
    # "allowed" (accepted the allow verdict, or overrode a hold/block) or
    # "flagged" (opened an investigation on it).
    decision: str
    # An opaque label from the risk registry (e.g. an external reference
    # entered when the wallet was designated) — kept for display only, never
    # trusted as a real case identifier. See `case_id` for that.
    case_ref: Optional[str] = None
    # The investigator's actual active case, when one exists — a real FK,
    # not the opaque `case_ref` string above. This is what actually links
    # the ledger entry to a case so it shows up in that case's Evidence
    # Trail; `case_ref` alone can't be trusted for that since it isn't
    # guaranteed to be a real case in this database.
    case_id: Optional[UUID] = None
    note: Optional[str] = None


class DepositDecisionResponse(BaseModel):
    recorded: bool = True
