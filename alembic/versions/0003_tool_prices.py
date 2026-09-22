"""Runtime-editable tool prices."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_tool_prices"
down_revision: str | None = "0002_source_class"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SEED = (
    ("search_listings", 0.01),
    ("get_property", 0.01),
    ("get_price_history", 0.02),
    ("get_market_stats", 0.02),
    ("get_comps", 0.02),
    ("check_listing_freshness", 0.02),
    ("verify_claim_corpus", 0.02),
    ("verify_claim_deep", 0.08),
    ("verify_url", 0.08),
    ("get_evidence", 0.01),
)


def upgrade() -> None:
    op.create_table(
        "tool_prices",
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("price_eur", sa.Numeric(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("tool"),
    )
    tool_prices = sa.table(
        "tool_prices",
        sa.column("tool", sa.Text),
        sa.column("price_eur", sa.Numeric),
    )
    op.bulk_insert(tool_prices, [{"tool": tool, "price_eur": price} for tool, price in _SEED])


def downgrade() -> None:
    op.drop_table("tool_prices")
