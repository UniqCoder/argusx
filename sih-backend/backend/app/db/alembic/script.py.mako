"""Generic single-database configuration with an async dbapi."""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "placeholder"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
