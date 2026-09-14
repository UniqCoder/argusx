"""traces: record where a trace's transaction data actually came from

Rationale: the prototype's demonstrable fraud scenarios used to live as a
hardcoded fixture in the frontend, which short-circuited the API entirely. The
badge that marked a result "simulated" was therefore decided by the client,
from an address prefix — a check that silently stops matching the moment the
addresses change, and that no server-side consumer (the PDF report, the
evidence ledger, an export) could see at all.

The scenarios now run through the real engine over a fixture explorer, and the
engine asserts the provenance itself, from which explorer actually answered:

    live             every address was answered by a public explorer
    seeded_scenario  every address was answered by the scenario fixture
    mixed            both — a seeded trail that reached live data, or the reverse

Both columns are nullable; rows written before this migration predate the
distinction and are left NULL rather than being assumed live.

Revision ID: 0006_trace_data_provenance
Revises: 0005_trace_honesty_fields
Create Date: 2026-09-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0006_trace_data_provenance'
down_revision: Union[str, None] = '0005_trace_honesty_fields'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('traces', sa.Column('data_source', sa.String(), nullable=True))
    op.add_column('traces', sa.Column('scenario_key', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('traces', 'scenario_key')
    op.drop_column('traces', 'data_source')
