"""app/schemas/check_wallet.py — VASP deposit chokepoint schemas."""
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import AlertAction, Chain


class CheckWalletRequest(BaseModel):
    address: str
    chain: Chain
    amount: float = Field(..., gt=0)


class CheckWalletResponse(BaseModel):
    risk_score: float = Field(..., ge=0.0, le=1.0)
    action: AlertAction
    case_ref: Optional[str] = None
