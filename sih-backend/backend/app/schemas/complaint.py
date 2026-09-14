"""app/schemas/complaint.py — Complaint request/response schemas with LLM NER enrichment."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Chain, SourcePlatform


class ComplaintWalletIn(BaseModel):
    """A wallet the complainant names in their report."""
    address: str
    chain: Chain


class ComplaintCreate(BaseModel):
    ncrp_ref: Optional[str] = None
    source_platform: SourcePlatform
    narrative_text: Optional[str] = None
    fraud_typology: Optional[str] = None
    amount_lost: Optional[float] = None
    filed_at: datetime
    state: Optional[str] = None
    district: Optional[str] = None
    # Wallets this complaint names. Without this field, ingestion could never
    # write complaint_wallets -- the ONLY table POST /api/v1/correlate reads --
    # so cross-victim correlation returned correlation_score 0.0 for every
    # wallet that existed and 404 for every wallet that did not, on any
    # database not seeded by scripts/generate_synthetic_ncrp.py.
    wallets: List[ComplaintWalletIn] = Field(default_factory=list)


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
