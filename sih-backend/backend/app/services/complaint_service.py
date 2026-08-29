"""
app/services/complaint_service.py — Complaint ingestion, listing, and LLM entity extraction service.

Architecture rule (rules.md §2):
  Routers delegate to services; services handle business logic & database access.
"""
import uuid
from typing import Optional, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.complaint import Complaint
from app.nlp import llm_ner
from app.schemas.complaint import ComplaintCreate, ComplaintDetailRead, ExtractedEntities


async def create_complaint(
    db: AsyncSession,
    complaint_in: ComplaintCreate,
) -> Complaint:
    """
    Ingest a new complaint into PostgreSQL.
    """
    complaint = Complaint(
        id=uuid.uuid4(),
        ncrp_ref=complaint_in.ncrp_ref,
        source_platform=complaint_in.source_platform.value,
        narrative_text=complaint_in.narrative_text,
        fraud_typology=complaint_in.fraud_typology,
        amount_lost=complaint_in.amount_lost,
        filed_at=complaint_in.filed_at,
        state=complaint_in.state,
        district=complaint_in.district,
    )
    db.add(complaint)
    await db.commit()
    await db.refresh(complaint)
    return complaint


async def list_complaints(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 25,
    state: Optional[str] = None,
    fraud_typology: Optional[str] = None,
) -> tuple[Sequence[Complaint], int]:
    """
    List complaints with optional filtering and pagination.
    Returns (items, total_count).
    """
    stmt = select(Complaint)
    count_stmt = select(func.count()).select_from(Complaint)

    if state:
        stmt = stmt.where(Complaint.state == state)
        count_stmt = count_stmt.where(Complaint.state == state)

    if fraud_typology:
        stmt = stmt.where(Complaint.fraud_typology == fraud_typology)
        count_stmt = count_stmt.where(Complaint.fraud_typology == fraud_typology)

    # Order by filed_at descending
    stmt = stmt.order_by(Complaint.filed_at.desc())
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    result = await db.execute(stmt)
    items = result.scalars().all()

    return items, total


async def get_complaint_by_id(
    db: AsyncSession,
    complaint_id: uuid.UUID,
) -> Optional[Complaint]:
    """Get a complaint by primary key UUID."""
    stmt = select(Complaint).where(Complaint.id == complaint_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_complaint_with_entities(
    db: AsyncSession,
    complaint_id: uuid.UUID,
) -> Optional[ComplaintDetailRead]:
    """
    Retrieve complaint details and enrich with local air-gapped LLM/spaCy extracted entities (Phase 6).
    """
    complaint = await get_complaint_by_id(db, complaint_id)
    if complaint is None:
        return None

    extracted_data = None
    if complaint.narrative_text:
        raw_entities = await llm_ner.extract_entities_from_narrative(complaint.narrative_text)
        extracted_data = ExtractedEntities.model_validate(raw_entities)

    res = ComplaintDetailRead.model_validate(complaint)
    res.extracted_entities = extracted_data
    return res
