"""
app/models/wallet.py — SQLAlchemy ORM for the wallets table.
DDL source: PRD §9.4.
"""
import uuid
from datetime import datetime

from sqlalchemy import NUMERIC, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Wallet(Base):
    __tablename__ = "wallets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    address: Mapped[str] = mapped_column(String, nullable=False)
    chain: Mapped[str] = mapped_column(String, nullable=False)  # BTC|ETH|TRON|BSC
    first_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    risk_score: Mapped[float | None] = mapped_column(NUMERIC(4, 3), nullable=True)
    risk_tier: Mapped[str | None] = mapped_column(String, nullable=True)
    vasp_identified: Mapped[str | None] = mapped_column(String, nullable=True)
    cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("address", "chain", name="uq_wallets_address_chain"),
        Index("idx_wallets_risk_tier", "risk_tier"),
    )
