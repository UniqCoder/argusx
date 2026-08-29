"""app/schemas/correlate.py — Cross-victim correlation schemas."""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, model_validator

from app.schemas.common import Chain
from app.schemas.complaint import ComplaintRead


class CorrelateRequest(BaseModel):
    wallet_id: Optional[UUID] = None
    address: Optional[str] = None
    chain: Optional[Chain] = None

    @model_validator(mode="after")
    def validate_lookup_key(self) -> "CorrelateRequest":
        has_id = self.wallet_id is not None
        has_addr = self.address is not None and self.chain is not None
        if has_id == has_addr:  # both truthy or both falsy
            raise ValueError(
                "Provide either wallet_id or (address + chain), not both or neither."
            )
        return self


class CorrelateResponse(BaseModel):
    correlation_score: float
    linked_complaints: List[ComplaintRead]
    distinct_geographies: int
    total_amount: float
