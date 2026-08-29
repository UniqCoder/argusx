"""app/schemas/complaint.py — Complaint request/response schemas with LLM NER enrichment."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import SourcePlatform


class ComplaintCreate(BaseModel):
    ncrp_ref: Optional[str] = None
    source_platform: SourcePlatform
    narrative_text: Optional[str] = None
    fraud_typology: Optional[str] = None
    amount_lost: Optional[float] = None
    filed_at: datetime
    state: Optional[str] = None
    district: Optional[str] = None


class ComplaintRead(BaseModel):
    id: UUID
    ncrp_ref: Optional[str] = None
    source_platform: SourcePlatform
    narrative_text: Optional[str] = None
    fraud_typology: Optional[str] = None
    amount_lost: Optional[float] = None
    filed_at: datetime
    state: Optional[str] = None
    district: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AmountMentioned(BaseModel):
    amount: float
    currency: str = "INR"


class CryptoAddressMentioned(BaseModel):
    address: str
    chain: str = "BTC"


class ExtractedEntities(BaseModel):
    suspect_names: List[str] = Field(default_factory=list)
    amounts_mentioned: List[AmountMentioned] = Field(default_factory=list)
    crypto_addresses: List[CryptoAddressMentioned] = Field(default_factory=list)
    dates_mentioned: List[str] = Field(default_factory=list)
    fraud_typology: Optional[str] = None
    summary: Optional[str] = None
    extractor_used: Optional[str] = None
    latency_ms: Optional[float] = None


class ComplaintDetailRead(ComplaintRead):
    """Enriched complaint response containing read-only NLP/LLM extracted entities (Phase 6)."""
    extracted_entities: Optional[ExtractedEntities] = None
