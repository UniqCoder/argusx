"""
app/models/complaint.py — SQLAlchemy ORM for complaints + complaint_wallets.
DDL source: PRD §9.4.
"""
import uuid
from datetime import datetime

from sqlalchemy import NUMERIC, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    ncrp_ref: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    source_platform: Mapped[str] = mapped_column(String, nullable=False)  # ncrp|sahyog|manual
    complainant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    narrative_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fraud_typology: Mapped[str | None] = mapped_column(String, nullable=True)
    amount_lost: Mapped[float | None] = mapped_column(NUMERIC(14, 2), nullable=True)
    filed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    state: Mapped[str | None] = mapped_column(String, nullable=True)
    district: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ComplaintWallet(Base):
    """Junction table — powers USP 1 (Cross-Victim Correlation)."""
    __tablename__ = "complaint_wallets"

    complaint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("complaints.id"),
        primary_key=True,
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("wallets.id"),
        primary_key=True,
    )
    reported_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
