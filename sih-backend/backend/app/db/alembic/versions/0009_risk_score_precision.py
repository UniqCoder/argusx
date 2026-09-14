"""wallets: widen risk_score precision from NUMERIC(4,3) to NUMERIC(5,4)

Rationale: app/services/risk_service.py computes and returns risk_score at
4-decimal precision (round(..., 4)) so a genuinely near-zero score (e.g.
0.0003) survives instead of collapsing to a bare 0.000 — see the
"risk score should not be 0 or 100 directly" fix. The wallets table column
was still NUMERIC(4,3) (3 decimal places, 1 integer digit), silently
truncating every persisted score back down to 3dp — a real precision loss
between what the API returns and what the DB stores, distinct from (and in
addition to) the Redis registry rounding fix in the same change. NUMERIC(5,4)
holds 1 integer digit + 4 fractional digits, exactly matching the API's
precision for the [0.0, 1.0] score range.

Revision ID: 0009_risk_score_precision
Revises: 0008_typologies_path_risk
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0009_risk_score_precision'
down_revision: Union[str, None] = '0008_typologies_path_risk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'wallets', 'risk_score',
        type_=sa.NUMERIC(precision=5, scale=4),
        existing_type=sa.NUMERIC(precision=4, scale=3),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'wallets', 'risk_score',
        type_=sa.NUMERIC(precision=4, scale=3),
        existing_type=sa.NUMERIC(precision=5, scale=4),
        existing_nullable=True,
    )
