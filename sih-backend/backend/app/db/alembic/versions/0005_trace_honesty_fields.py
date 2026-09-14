"""traces + taint_nodes: record how far a trace actually got, why it stopped, what it was seeded with, and which branches were deliberately not followed

Rationale (see app/engine/taint.py): the engine used to return a trace with no
way to distinguish "reached the depth you asked for" from "stopped at hop 3",
and no record of the tainted seed — which was hardcoded to 1.0 native unit, so
every taint_fraction was arithmetic on an invented number. Branches pruned by
the dust floor were dropped silently, which made correct haircut dilution look
like a truncated or broken graph.

These columns persist that context so GET /engine/trace/{id}, the PDF report
and the dashboard graph all describe the same trace with the same caveats.
All are nullable — existing rows predate the accounting and are left NULL
rather than back-filled with numbers nobody measured.

Revision ID: 0005_trace_honesty_fields
Revises: 0004_anchor_case_id
Create Date: 2026-09-12 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0005_trace_honesty_fields'
down_revision: Union[str, None] = '0004_anchor_case_id'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('traces', sa.Column('depth_reached', sa.SmallInteger(), nullable=True))
    op.add_column('traces', sa.Column('termination_reason', sa.String(), nullable=True))
    op.add_column('traces', sa.Column('seed_value', sa.Numeric(24, 8), nullable=True))
    op.add_column('traces', sa.Column('seed_basis', sa.String(), nullable=True))
    op.add_column('traces', sa.Column('pruned_branch_count', sa.Integer(), nullable=True))
    op.add_column('traces', sa.Column('pruned_branch_value', sa.Numeric(24, 8), nullable=True))

    # Which asset the trace followed. Taint apportionment is only coherent
    # within one asset: the explorers returned ERC-20/TRC-20 token amounts in
    # the same field as native-coin amounts, so a token-active wallet had its
    # USDT and native inflows summed into one meaningless haircut denominator.
    op.add_column('traces', sa.Column('asset', sa.String(), nullable=True))
    op.add_column('traces', sa.Column('asset_basis', sa.String(), nullable=True))
    op.add_column('traces', sa.Column('other_asset_branch_count', sa.Integer(), nullable=True))

    op.add_column('taint_nodes', sa.Column('pruned_child_count', sa.Integer(), nullable=True))
    op.add_column('taint_nodes', sa.Column('pruned_child_value', sa.Numeric(24, 8), nullable=True))
    op.add_column('taint_nodes', sa.Column('other_asset_child_count', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('taint_nodes', 'other_asset_child_count')
    op.drop_column('taint_nodes', 'pruned_child_value')
    op.drop_column('taint_nodes', 'pruned_child_count')

    op.drop_column('traces', 'other_asset_branch_count')
    op.drop_column('traces', 'asset_basis')
    op.drop_column('traces', 'asset')

    op.drop_column('traces', 'pruned_branch_value')
    op.drop_column('traces', 'pruned_branch_count')
    op.drop_column('traces', 'seed_basis')
    op.drop_column('traces', 'seed_value')
    op.drop_column('traces', 'termination_reason')
    op.drop_column('traces', 'depth_reached')
