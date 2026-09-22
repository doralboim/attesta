"""Add observations.source_class (portal | cadastral | registry | feed)."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_source_class"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "observations",
        sa.Column("source_class", sa.Text(), nullable=False, server_default="portal"),
    )


def downgrade() -> None:
    op.drop_column("observations", "source_class")
