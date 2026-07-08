"""Shared tool implementations — single source of truth for REST and MCP."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PriceEvent, Property, PropertyObservation


class SearchFilters(BaseModel):
    region: str | None = None
    city: str | None = None
    typology: str | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    max_staleness_score: float = 1.0
    include_inactive: bool = False
    limit: int = Field(default=20, ge=1, le=50)


class PropertySummary(BaseModel):
    id: uuid.UUID
    region: str
    city: str | None
    current_price_eur: float | None
    days_on_market: int | None
    staleness_score: float | None
    is_active: bool
    sources: list[str]


class ToolService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def search_listings(self, filters: SearchFilters) -> dict:
        stmt = select(Property)
        if not filters.include_inactive:
            stmt = stmt.where(Property.is_active.is_(True))
        if filters.region:
            stmt = stmt.where(Property.region == filters.region)
        if filters.min_price_eur is not None:
            stmt = stmt.where(Property.current_price_eur >= filters.min_price_eur)
        if filters.max_price_eur is not None:
            stmt = stmt.where(Property.current_price_eur <= filters.max_price_eur)
        if filters.max_staleness_score < 1.0:
            stmt = stmt.where(Property.staleness_score <= filters.max_staleness_score)

        props = (await self.session.execute(stmt)).scalars().all()
        if filters.city:
            props = [
                p
                for p in props
                if str(p.canonical_attrs.get("city", "")).lower() == filters.city.lower()
            ]
        if filters.typology:
            props = [
                p
                for p in props
                if str(p.canonical_attrs.get("typology", "")).lower() == filters.typology.lower()
            ]
        props = props[: filters.limit]
        summaries = [await self._to_summary(p) for p in props]
        return {
            "count": len(summaries),
            "listings": [s.model_dump(mode="json") for s in summaries],
        }

    async def get_property(self, property_id: uuid.UUID) -> dict | None:
        prop = await self.session.get(Property, property_id)
        if not prop:
            return None
        summary = await self._to_summary(prop)
        return {
            **summary.model_dump(mode="json"),
            "canonical_attrs": prop.canonical_attrs,
            "first_seen": prop.first_seen.isoformat(),
            "last_seen": prop.last_seen.isoformat(),
        }

    async def get_price_history(self, property_id: uuid.UUID) -> dict | None:
        prop = await self.session.get(Property, property_id)
        if not prop:
            return None
        events = (
            await self.session.execute(
                select(PriceEvent)
                .where(PriceEvent.property_id == property_id)
                .order_by(PriceEvent.event_at)
            )
        ).scalars().all()
        return {
            "property_id": str(property_id),
            "days_on_market": prop.days_on_market,
            "events": [
                {
                    "event_at": e.event_at.isoformat(),
                    "kind": e.kind,
                    "price_eur": float(e.price_eur) if e.price_eur else None,
                    "source": e.source,
                    "snapshot_id": e.snapshot_id,
                }
                for e in events
            ],
        }

    async def get_market_stats(self, region: str | None, city: str | None) -> dict:
        stmt = select(Property)
        if region:
            stmt = stmt.where(Property.region == region)
        props = (await self.session.execute(stmt)).scalars().all()
        if city:
            props = [p for p in props if str(p.canonical_attrs.get("city", "")).lower() == city.lower()]

        if not props:
            return {
                "region": region,
                "city": city,
                "active_listings": 0,
                "as_of": datetime.now(UTC).isoformat(),
            }

        prices = sorted(float(p.current_price_eur) for p in props if p.current_price_eur)
        median = prices[len(prices) // 2] if prices else None
        stale = sum(1 for p in props if (p.staleness_score or 0) >= 0.6) / len(props)

        return {
            "region": region,
            "city": city,
            "active_listings": len(props),
            "median_price_eur": median,
            "stale_listing_rate": round(stale, 3),
            "as_of": datetime.now(UTC).isoformat(),
        }

    async def check_listing_freshness(self, property_id: uuid.UUID) -> dict | None:
        prop = await self.session.get(Property, property_id)
        if not prop:
            return None
        days_since = (datetime.now(UTC) - prop.last_seen.replace(tzinfo=UTC)).days
        if not prop.is_active or (prop.staleness_score or 0) >= 0.7:
            rec = "Treat as unavailable — likely delisted or phantom."
        elif (prop.staleness_score or 0) >= 0.4:
            rec = "Verify availability — may be stale."
        else:
            rec = "Listing appears fresh."
        return {
            "property_id": str(property_id),
            "is_active": prop.is_active,
            "staleness_score": prop.staleness_score,
            "last_seen": prop.last_seen.isoformat(),
            "days_since_last_seen": days_since,
            "recommendation": rec,
        }

    async def _to_summary(self, prop: Property) -> PropertySummary:
        from app.db.models import Observation

        links = (
            await self.session.execute(
                select(PropertyObservation).where(PropertyObservation.property_id == prop.id)
            )
        ).scalars().all()
        source_names: list[str] = []
        for link in links:
            obs = await self.session.get(Observation, link.observation_id)
            if obs and obs.source not in source_names:
                source_names.append(obs.source)
        return PropertySummary(
            id=prop.id,
            region=prop.region,
            city=prop.canonical_attrs.get("city"),
            current_price_eur=float(prop.current_price_eur) if prop.current_price_eur else None,
            days_on_market=prop.days_on_market,
            staleness_score=prop.staleness_score,
            is_active=prop.is_active,
            sources=source_names,
        )
