"""SQLAlchemy 2.0 models — authoritative schema per attesta-architecture.md §3."""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

# pgvector optional — use Text fallback for sqlite tests
try:
    from pgvector.sqlalchemy import Vector

    HAS_PGVECTOR = True
except ImportError:
    HAS_PGVECTOR = False


class Base(DeclarativeBase):
    pass


class Snapshot(Base):
    """Append-only provenance substrate. No UPDATE/DELETE paths in application code."""

    __tablename__ = "snapshots"
    __table_args__ = (UniqueConstraint("source", "url", "content_hash", name="uq_snapshot"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)

    observations: Mapped[list[Observation]] = relationship(back_populates="snapshot")


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (Index("ix_observations_source_listing", "source", "source_listing_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    snapshot_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("snapshots.id"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_listing_id: Mapped[str] = mapped_column(Text, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    price_eur: Mapped[float | None] = mapped_column(Numeric)
    status: Mapped[str | None] = mapped_column(Text)
    attrs: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    geo_lat: Mapped[float | None] = mapped_column(Float)
    geo_lon: Mapped[float | None] = mapped_column(Float)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(384) if HAS_PGVECTOR else Text,  # type: ignore[misc]
        nullable=True,
    )

    snapshot: Mapped[Snapshot] = relationship(back_populates="observations")
    property_links: Mapped[list[PropertyObservation]] = relationship(back_populates="observation")


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_attrs: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    staleness_score: Mapped[float | None] = mapped_column(Float)
    current_price_eur: Mapped[float | None] = mapped_column(Numeric)
    days_on_market: Mapped[int | None] = mapped_column(Integer)
    consecutive_ingest_misses: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    observations: Mapped[list[PropertyObservation]] = relationship(back_populates="property")
    price_events: Mapped[list[PriceEvent]] = relationship(back_populates="property")


class PropertyObservation(Base):
    __tablename__ = "property_observations"

    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), primary_key=True)
    observation_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("observations.id"), primary_key=True)
    match_confidence: Mapped[float] = mapped_column(Float, nullable=False)

    property: Mapped[Property] = relationship(back_populates="observations")
    observation: Mapped[Observation] = relationship(back_populates="property_links")


class PriceEvent(Base):
    __tablename__ = "price_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    property_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("properties.id"), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    price_eur: Mapped[float | None] = mapped_column(Numeric)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("snapshots.id"))

    property: Mapped[Property] = relationship(back_populates="price_events")


class ApiKey(Base):
    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(Text, primary_key=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(Text)
    stripe_subscription_item_id: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[str] = mapped_column(Text, nullable=False, default="metered")
    monthly_free_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=200)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class UsageEvent(Base):
    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    rail: Mapped[str] = mapped_column(Text, nullable=False)
    key_hash: Mapped[str | None] = mapped_column(Text)
    payer_address: Mapped[str | None] = mapped_column(Text)
    tool: Mapped[str] = mapped_column(Text, nullable=False)
    price_eur: Mapped[float] = mapped_column(Numeric, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    x402_receipt: Mapped[dict | None] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=True)
    stripe_pushed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Attestation(Base):
    __tablename__ = "attestations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    verdicts: Mapped[dict] = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_hashes: Mapped[list[str]] = mapped_column(ARRAY(Text).with_variant(JSON, "sqlite"), nullable=False)
    jws: Mapped[str] = mapped_column(Text, nullable=False)
    usage_event_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("usage_events.id"))
