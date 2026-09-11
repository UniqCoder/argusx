"""
app/engine/anchors.py — Layer 0: ground-truth anchor registry.

Nothing enters the taint engine as "tainted" without one of these. See
ARGUS-ENGINE-V2.md §Layer 0 for the attestation-class table.
"""
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engine import Anchor
from app.schemas.engine import AnchorCreate


class DuplicateAnchorError(Exception):
    """Raised when (address, chain, source_ref) already has an anchor."""


async def create_anchor(db: AsyncSession, body: AnchorCreate) -> Anchor:
    """
    Register an externally-attested anchor.

    Anti-feedback-loop guard (ARGUS-ENGINE-V2.md §Layer 0 / v1's documented
    open risk in docs/incidents — "a human-mediated feedback path from model
    scores"): this is the ONLY writer of the anchors table reachable from the
    API, and it always persists system_generated=False. Nothing computed by
    this system (a triage score, a typology match, a decision) can promote
    itself into ground truth. The database CHECK constraint
    ck_anchor_never_system_generated backs this even against a direct DB write.
    """
    anchor = Anchor(
        address=body.address.strip(),
        chain=body.chain.value,
        attestation_class=body.attestation_class.value,
        attestation_type=body.attestation_type.value,
        source_ref=body.source_ref.strip(),
        asserted_by=body.asserted_by.strip(),
        asserted_at=body.asserted_at or datetime.now(timezone.utc),
        victim_amount_inr=body.victim_amount_inr,
        evidence_uri=body.evidence_uri,
        system_generated=False,
    )
    db.add(anchor)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateAnchorError(
            f"Anchor already exists for ({body.address}, {body.chain.value}, {body.source_ref})"
        ) from exc
    await db.refresh(anchor)
    return anchor


async def get_anchor(db: AsyncSession, anchor_id: UUID) -> Anchor | None:
    res = await db.execute(select(Anchor).where(Anchor.id == anchor_id))
    return res.scalar_one_or_none()
