"""traces: persist detected laundering typologies and the path-risk summary

Rationale: app/engine/typologies.py names the specific patterns a trace
exhibits (structuring, mixer contact, rapid movement to an exchange, ...) and
rolls them into a four-part path-risk breakdown -- Origin / Layering / Mixer
Exposure / Cash-out Proximity -- per IMPROVEMENTS_PLANNED.md item 5
("money-flow path summary... a summary layer over the nodes list POST /trace
already returns"). This is explanation, never a decision input: the decision
engine (app/engine/decision.py) does not read either of these columns, and
IMPROVEMENTS_PLANNED.md explicitly rejects a fused confidence score that could
drive a block.

Persisted so GET /engine/trace/{id} and the PDF report describe the same
analysis the live trace showed. Nullable; rows written before this migration
predate the analysis and are left NULL rather than back-filled with a guess.

Revision ID: 0008_typologies_path_risk
Revises: 0007_roles_clustering_crosschain
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0008_typologies_path_risk'
down_revision: Union[str, None] = '0007_roles_clustering_crosschain'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('traces', sa.Column('typologies', sa.JSON(), nullable=True))
    op.add_column('traces', sa.Column('path_risk', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('traces', 'path_risk')
    op.drop_column('traces', 'typologies')
