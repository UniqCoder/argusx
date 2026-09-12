"""anchors: add case_id so a case's Evidence Trail can find its real anchor/trace/decision events

Revision ID: 0004_anchor_case_id
Revises: 0003_taint_node_parent_edge
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0004_anchor_case_id'
down_revision: Union[str, None] = '0003_taint_node_parent_edge'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'anchors',
        sa.Column('case_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_anchors_case_id', 'anchors', 'cases', ['case_id'], ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_anchors_case_id', 'anchors', type_='foreignkey')
    op.drop_column('anchors', 'case_id')
