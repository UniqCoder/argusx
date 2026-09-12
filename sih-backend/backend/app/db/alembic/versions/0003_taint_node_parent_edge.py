"""taint_nodes: add parent_address/tx_hash/tx_amount for real branching graph edges

Revision ID: 0003_taint_node_parent_edge
Revises: 0002_engine_layer_tables
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0003_taint_node_parent_edge'
down_revision: Union[str, None] = '0002_engine_layer_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('taint_nodes', sa.Column('parent_address', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('tx_hash', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('tx_amount', sa.Numeric(24, 8), nullable=True))


def downgrade() -> None:
    op.drop_column('taint_nodes', 'tx_amount')
    op.drop_column('taint_nodes', 'tx_hash')
    op.drop_column('taint_nodes', 'parent_address')
