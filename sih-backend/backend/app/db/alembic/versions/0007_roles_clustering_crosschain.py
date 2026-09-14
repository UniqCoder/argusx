"""taint_nodes + traces: persist roles, clustering and cross-chain link provenance

Rationale: a graph of addresses and arrows told an investigator very little on
its own -- the question a case turns on ("who is the fraudster, where did the
money end up") was left entirely to the reader. app/engine/roles.py and
clustering.py now read the finished graph once and derive that; this persists
the result so GET /engine/trace/{id} and the PDF report describe the same
graph the live trace showed, rather than re-deriving it (and potentially
drifting) on every read.

app/engine/crosschain.py also lets a bridge deposit be matched to a release on
another chain by value and time -- a correlation, not a proof -- and
`link_basis`/`link_confidence`/`link_detail` record which kind of edge reached
each node so the UI never draws a heuristic the same way as a signed
transaction.

All new columns are nullable; rows written before this migration predate the
analysis and are left NULL rather than back-filled with a guess.

Revision ID: 0007_roles_clustering_crosschain
Revises: 0006_trace_data_provenance
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0007_roles_clustering_crosschain'
down_revision: Union[str, None] = '0006_trace_data_provenance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('taint_nodes', sa.Column('role', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('role_basis', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('description', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('cluster_id', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('cluster_label', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('value_in', sa.Numeric(24, 8), nullable=True))
    op.add_column('taint_nodes', sa.Column('value_out', sa.Numeric(24, 8), nullable=True))
    op.add_column('taint_nodes', sa.Column('value_parked', sa.Numeric(24, 8), nullable=True))
    op.add_column('taint_nodes', sa.Column('link_basis', sa.String(), nullable=True))
    op.add_column('taint_nodes', sa.Column('link_confidence', sa.Numeric(4, 3), nullable=True))
    op.add_column('taint_nodes', sa.Column('link_detail', sa.String(), nullable=True))

    op.add_column('traces', sa.Column('inbound_sources', sa.JSON(), nullable=True))
    op.add_column('traces', sa.Column('clusters', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('traces', 'clusters')
    op.drop_column('traces', 'inbound_sources')

    op.drop_column('taint_nodes', 'link_detail')
    op.drop_column('taint_nodes', 'link_confidence')
    op.drop_column('taint_nodes', 'link_basis')
    op.drop_column('taint_nodes', 'value_parked')
    op.drop_column('taint_nodes', 'value_out')
    op.drop_column('taint_nodes', 'value_in')
    op.drop_column('taint_nodes', 'cluster_label')
    op.drop_column('taint_nodes', 'cluster_id')
    op.drop_column('taint_nodes', 'description')
    op.drop_column('taint_nodes', 'role_basis')
    op.drop_column('taint_nodes', 'role')
