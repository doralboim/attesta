"""Ingestion pipeline: PII strip → snapshot → observation → diff → delist detection."""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Observation, Property, PropertyObservation, Snapshot
from app.ingestion.base import BaseCollector, RawListing
from app.ingestion.pii_strip import strip_pii_from_record
from app.ingestion.snapshot_store import get_snapshot_store, snapshot_payload
from app.resolution.embeddings import embed_listing

logger = structlog.get_logger()


class IngestionService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.store = get_snapshot_store()
        self.settings = get_settings()

    async def ingest_collector(self, collector: BaseCollector) -> dict[str, int]:
        listings = await collector.fetch_listings()
        stats = {"snapshots": 0, "observations": 0, "price_changes": 0, "delisted": 0}
        seen_ids: set[str] = set()

        for listing in listings:
            seen_ids.add(listing.source_listing_id)
            created, event = await self._ingest_listing(listing)
            if created:
                stats["snapshots"] += 1
                stats["observations"] += 1
            if event == "price_change":
                stats["price_changes"] += 1
            elif event == "delisted":
                stats["delisted"] += 1

        delisted = await self._detect_delistings(collector.source_name, seen_ids)
        stats["delisted"] += delisted

        await self.session.commit()
        logger.info("ingestion_complete", source=collector.source_name, **stats)
        return stats

    async def ingest_one(self, listing: RawListing) -> Observation:
        """Ingest a single listing without a full-source delist sweep. Does not commit."""
        created, _ = await self._ingest_listing(listing)
        if created:
            await self.session.flush()
        obs = await self._latest_observation(listing.source, listing.source_listing_id)
        if obs is None:
            msg = f"ingest_one produced no observation for {listing.source}/{listing.source_listing_id}"
            raise RuntimeError(msg)
        return obs

    async def _ingest_listing(self, listing: RawListing) -> tuple[bool, str | None]:
        payload_dict = strip_pii_from_record(listing.raw_payload or listing.attrs)
        payload = snapshot_payload(payload_dict)
        content_hash, storage_key = await self.store.write(listing.source, listing.url, payload)

        existing_snap = await self.session.execute(
            select(Snapshot).where(
                Snapshot.source == listing.source,
                Snapshot.url == listing.url,
                Snapshot.content_hash == content_hash,
            )
        )
        if existing_snap.scalar_one_or_none():
            return False, None

        snap = Snapshot(
            source=listing.source,
            url=listing.url,
            fetched_at=listing.observed_at,
            content_hash=content_hash,
            storage_key=storage_key,
            http_status=200,
        )
        self.session.add(snap)
        await self.session.flush()

        prev = await self._latest_observation(listing.source, listing.source_listing_id)
        event: str | None = None
        if prev:
            if prev.price_eur != listing.price_eur and listing.price_eur is not None:
                event = "price_change"
            if listing.status == "delisted":
                event = "delisted"

        embedding = await embed_listing(listing)
        obs = Observation(
            snapshot_id=snap.id,
            source=listing.source,
            source_listing_id=listing.source_listing_id,
            observed_at=listing.observed_at,
            price_eur=listing.price_eur,
            status=listing.status,
            attrs=listing.attrs,
            geo_lat=listing.geo_lat,
            geo_lon=listing.geo_lon,
            embedding=embedding,
            source_class=listing.source_class,
        )
        self.session.add(obs)
        return True, event

    async def _latest_observation(self, source: str, source_listing_id: str) -> Observation | None:
        result = await self.session.execute(
            select(Observation)
            .where(
                Observation.source == source,
                Observation.source_listing_id == source_listing_id,
            )
            .order_by(Observation.observed_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _detect_delistings(self, source: str, seen_listing_ids: set[str]) -> int:
        """Mark listings absent for N consecutive ingests as delisted."""
        threshold = self.settings.delist_miss_threshold
        delisted_count = 0

        active_observations = (
            (
                await self.session.execute(
                    select(Observation)
                    .where(Observation.source == source)
                    .where(Observation.status != "delisted")
                    .order_by(Observation.source_listing_id, Observation.observed_at.desc())
                )
            )
            .scalars()
            .all()
        )

        latest_by_listing: dict[str, Observation] = {}
        for obs in active_observations:
            if obs.source_listing_id not in latest_by_listing:
                latest_by_listing[obs.source_listing_id] = obs

        for listing_id, last_obs in latest_by_listing.items():
            if listing_id in seen_listing_ids:
                await self._reset_misses_for_listing(source, listing_id)
                continue

            miss_streak = await self._increment_miss_streak(source, listing_id)
            if miss_streak < threshold:
                continue
            if last_obs.status == "delisted":
                continue
            if await self._record_delisted(last_obs):
                delisted_count += 1

        return delisted_count

    async def _record_delisted(self, last_obs: Observation) -> bool:
        from datetime import UTC, datetime

        snap = await self.session.get(Snapshot, last_obs.snapshot_id)
        url = snap.url if snap else f"unknown://{last_obs.source}/{last_obs.source_listing_id}"
        now = datetime.now(UTC)
        listing = RawListing(
            source=last_obs.source,
            source_listing_id=last_obs.source_listing_id,
            url=url,
            observed_at=now,
            price_eur=float(last_obs.price_eur) if last_obs.price_eur else None,
            status="delisted",
            attrs={**last_obs.attrs, "delisted_reason": "consecutive_ingest_miss"},
            geo_lat=last_obs.geo_lat,
            geo_lon=last_obs.geo_lon,
            raw_payload={
                "delisted": True,
                "source_listing_id": last_obs.source_listing_id,
                "observed_at": now.isoformat(),
            },
        )
        created, _ = await self._ingest_listing(listing)
        return created

    async def _reset_misses_for_listing(self, source: str, listing_id: str) -> None:
        props = await self._properties_for_source_listing(source, listing_id)
        for prop in props:
            prop.consecutive_ingest_misses = 0

    async def _increment_miss_streak(self, source: str, listing_id: str) -> int:
        props = await self._properties_for_source_listing(source, listing_id)
        if not props:
            return 1
        max_miss = 0
        for prop in props:
            prop.consecutive_ingest_misses += 1
            max_miss = max(max_miss, prop.consecutive_ingest_misses)
        return max_miss

    async def _properties_for_source_listing(self, source: str, listing_id: str) -> list[Property]:
        observations = (
            (
                await self.session.execute(
                    select(Observation).where(
                        Observation.source == source,
                        Observation.source_listing_id == listing_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        if not observations:
            return []

        obs_ids = [o.id for o in observations]
        links = (
            (
                await self.session.execute(
                    select(PropertyObservation).where(PropertyObservation.observation_id.in_(obs_ids))
                )
            )
            .scalars()
            .all()
        )
        prop_ids = {link.property_id for link in links}
        if not prop_ids:
            return []
        return list((await self.session.execute(select(Property).where(Property.id.in_(prop_ids)))).scalars().all())
