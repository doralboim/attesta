"""Initial schema — provenance substrate, corpus, billing, attestations."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    op.create_table(
        "snapshots",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "url", "content_hash", name="uq_snapshot"),
    )

    op.create_table(
        "api_keys",
        sa.Column("key_hash", sa.Text(), nullable=False),
        sa.Column("stripe_customer_id", sa.Text(), nullable=True),
        sa.Column("stripe_subscription_item_id", sa.Text(), nullable=True),
        sa.Column("plan", sa.Text(), nullable=False, server_default="metered"),
        sa.Column("monthly_free_calls", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("key_hash"),
    )

    op.create_table(
        "properties",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("canonical_attrs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("region", sa.Text(), nullable=False),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("staleness_score", sa.Float(), nullable=True),
        sa.Column("current_price_eur", sa.Numeric(), nullable=True),
        sa.Column("days_on_market", sa.Integer(), nullable=True),
        sa.Column("consecutive_ingest_misses", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_listing_id", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_eur", sa.Numeric(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column("attrs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("geo_lat", sa.Float(), nullable=True),
        sa.Column("geo_lon", sa.Float(), nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_observations_source_listing",
        "observations",
        ["source", "source_listing_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "usage_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("rail", sa.Text(), nullable=False),
        sa.Column("key_hash", sa.Text(), nullable=True),
        sa.Column("payer_address", sa.Text(), nullable=True),
        sa.Column("tool", sa.Text(), nullable=False),
        sa.Column("price_eur", sa.Numeric(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("x402_receipt", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("stripe_pushed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id"),
    )

    op.create_table(
        "attestations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claim", sa.Text(), nullable=False),
        sa.Column("verdicts", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_hashes", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("jws", sa.Text(), nullable=False),
        sa.Column("usage_event_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["usage_event_id"], ["usage_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "price_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("price_eur", sa.Numeric(), nullable=True),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("snapshot_id", sa.BigInteger(), nullable=True),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["snapshot_id"], ["snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "property_observations",
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observation_id", sa.BigInteger(), nullable=False),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["observation_id"], ["observations.id"]),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.PrimaryKeyConstraint("property_id", "observation_id"),
    )


def downgrade() -> None:
    op.drop_table("property_observations")
    op.drop_table("price_events")
    op.drop_table("attestations")
    op.drop_table("usage_events")
    op.drop_index("ix_observations_source_listing", table_name="observations")
    op.drop_table("observations")
    op.drop_table("properties")
    op.drop_table("api_keys")
    op.drop_table("snapshots")
    op.execute(sa.text("DROP EXTENSION IF EXISTS vector"))
