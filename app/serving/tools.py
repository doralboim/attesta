"""Shared tool implementations — single source of truth for REST and MCP."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from statistics import median

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Observation, PriceEvent, Property, PropertyObservation
from app.resolution.matcher import geo_distance_km
from app.resolution.staleness import (
    components_dict,
    compute_staleness,
    price_per_m2,
)
from app.serving.aggregates import area_within_tolerance, euro_m2_stats
from app.serving.envelope import (
    market_envelope,
    market_from_region,
    unsupported_market_envelope,
)


class SearchFilters(BaseModel):
    region: str | None = None
    city: str | None = None
    typology: str | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    max_staleness_score: float = 1.0
    include_inactive: bool = False
    limit: int = Field(default=20, ge=1, le=50)


class MarketStatsFilters(BaseModel):
    region: str | None = None
    city: str | None = None
    typology: str | None = None
    min_area_m2: float | None = None
    max_area_m2: float | None = None


class CompsFilters(BaseModel):
    region: str
    city: str | None = None
    typology: str | None = None
    area_m2: float = Field(gt=0)
    area_tolerance_pct: float = Field(default=15.0, ge=0, le=100)
    geo_radius_m: float | None = Field(default=None, gt=0)
    property_id: uuid.UUID | None = None
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
            props = [p for p in props if str(p.canonical_attrs.get("city", "")).lower() == filters.city.lower()]
        if filters.typology:
            props = [p for p in props if str(p.canonical_attrs.get("typology", "")).lower() == filters.typology.lower()]
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
        components = await self._staleness_components(prop)
        return {
            **summary.model_dump(mode="json"),
            "canonical_attrs": prop.canonical_attrs,
            "first_seen": prop.first_seen.isoformat(),
            "last_seen": prop.last_seen.isoformat(),
            "staleness_components": components,
        }

    async def get_price_history(self, property_id: uuid.UUID) -> dict | None:
        prop = await self.session.get(Property, property_id)
        if not prop:
            return None
        events = (
            (
                await self.session.execute(
                    select(PriceEvent).where(PriceEvent.property_id == property_id).order_by(PriceEvent.event_at)
                )
            )
            .scalars()
            .all()
        )
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

    async def get_market_stats(self, filters: MarketStatsFilters) -> dict:
        market = market_from_region(filters.region)
        coverage: dict = {
            "market": market or (filters.region.split("-")[0].upper() if filters.region else "unknown"),
            "asset_type": "residential_ask",
        }
        if filters.region:
            coverage["region"] = filters.region
        if filters.city:
            coverage["city"] = filters.city
        if filters.typology:
            coverage["typology"] = filters.typology

        if market is None:
            return unsupported_market_envelope(region=filters.region, city=filters.city)

        props = await self._filter_properties(
            region=filters.region,
            city=filters.city,
            typology=filters.typology,
            min_area_m2=filters.min_area_m2,
            max_area_m2=filters.max_area_m2,
            active_only=True,
        )

        limitations: list[str] = []
        empty_data = {
            "median_price_eur": None,
            "median_price_per_m2": None,
            "p25_price_per_m2": None,
            "p75_price_per_m2": None,
            "inventory_active": 0,
            "stale_rate": None,
            "median_days_on_market": None,
            "sample_size": 0,
        }
        if not props:
            return market_envelope(
                empty_data,
                coverage=coverage,
                limitations=["empty_corpus"],
            )

        prices = sorted(float(p.current_price_eur) for p in props if p.current_price_eur)
        median_price = float(median(prices)) if prices else None

        ppm2_vals: list[float] = []
        for p in props:
            ppm2 = price_per_m2(
                float(p.current_price_eur) if p.current_price_eur else None,
                p.canonical_attrs.get("area_m2"),
            )
            if ppm2 is not None:
                ppm2_vals.append(ppm2)
        m2_stats = euro_m2_stats(ppm2_vals)
        if m2_stats["sample_size"] == 0:
            limitations.append("no_area_for_price_per_m2")

        stale_rate = round(
            sum(1 for p in props if (p.staleness_score or 0) >= 0.6) / len(props),
            3,
        )
        dom = [p.days_on_market for p in props if p.days_on_market is not None]
        median_dom = int(median(dom)) if dom else None

        cut_rate = await self._price_cut_rate_30d([p.id for p in props])
        data = {
            "median_price_eur": round(median_price, 2) if median_price is not None else None,
            "median_price_per_m2": m2_stats["median_price_per_m2"],
            "p25_price_per_m2": m2_stats["p25_price_per_m2"],
            "p75_price_per_m2": m2_stats["p75_price_per_m2"],
            "inventory_active": len(props),
            "stale_rate": stale_rate,
            "median_days_on_market": median_dom,
            "sample_size": m2_stats["sample_size"],
        }
        if cut_rate is not None:
            data["price_cut_rate_30d"] = cut_rate
        else:
            limitations.append("price_cut_rate_unavailable")

        return market_envelope(data, coverage=coverage, limitations=limitations)

    async def get_comps(self, filters: CompsFilters) -> dict:
        market = market_from_region(filters.region)
        coverage: dict = {
            "market": market or filters.region.split("-")[0].upper(),
            "asset_type": "residential_ask",
            "region": filters.region,
        }
        if filters.city:
            coverage["city"] = filters.city
        if filters.typology:
            coverage["typology"] = filters.typology

        if market is None:
            return unsupported_market_envelope(region=filters.region, city=filters.city)

        props = await self._filter_properties(
            region=filters.region,
            city=filters.city,
            typology=filters.typology,
            active_only=True,
        )

        anchor_lat, anchor_lon = await self._resolve_geo_anchor(filters, props)

        comps: list[dict] = []
        for p in props:
            if filters.property_id and p.id == filters.property_id:
                continue
            area = _as_float(p.canonical_attrs.get("area_m2"))
            if area is None:
                continue
            if not area_within_tolerance(area, filters.area_m2, filters.area_tolerance_pct):
                continue
            if filters.geo_radius_m is not None:
                if anchor_lat is None or anchor_lon is None:
                    continue
                plat = _as_float(p.canonical_attrs.get("geo_lat"))
                plon = _as_float(p.canonical_attrs.get("geo_lon"))
                if plat is None or plon is None:
                    continue
                if geo_distance_km(anchor_lat, anchor_lon, plat, plon) * 1000 > filters.geo_radius_m:
                    continue

            ppm2 = price_per_m2(
                float(p.current_price_eur) if p.current_price_eur else None,
                area,
            )
            if ppm2 is None:
                continue
            summary = await self._to_summary(p)
            comps.append(
                {
                    "property_id": str(p.id),
                    "price_eur": summary.current_price_eur,
                    "area_m2": area,
                    "price_per_m2": round(ppm2, 2),
                    "staleness_score": summary.staleness_score,
                    "sources": summary.sources,
                    "city": summary.city,
                    "typology": p.canonical_attrs.get("typology"),
                }
            )

        comps = comps[: filters.limit]
        m2_stats = euro_m2_stats([c["price_per_m2"] for c in comps])
        limitations: list[str] = []
        if len(comps) < 5:
            limitations.append("sample_size_lt_5")

        return market_envelope(
            {
                "median_price_per_m2": m2_stats["median_price_per_m2"],
                "sample_size": len(comps),
                "comps": comps,
            },
            coverage=coverage,
            limitations=limitations,
        )

    async def check_listing_freshness(self, property_id: uuid.UUID) -> dict | None:
        prop = await self.session.get(Property, property_id)
        if not prop:
            return None
        days_since = (datetime.now(UTC) - prop.last_seen.replace(tzinfo=UTC)).days
        components = await self._staleness_components(prop)
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
            "staleness_components": components,
            "last_seen": prop.last_seen.isoformat(),
            "days_since_last_seen": days_since,
            "recommendation": rec,
        }

    async def _resolve_geo_anchor(
        self, filters: CompsFilters, props: list[Property]
    ) -> tuple[float | None, float | None]:
        if filters.geo_radius_m is None:
            return None, None
        if filters.property_id:
            anchor = await self.session.get(Property, filters.property_id)
            if anchor:
                return (
                    _as_float(anchor.canonical_attrs.get("geo_lat")),
                    _as_float(anchor.canonical_attrs.get("geo_lon")),
                )
        coords = [
            (_as_float(p.canonical_attrs.get("geo_lat")), _as_float(p.canonical_attrs.get("geo_lon"))) for p in props
        ]
        valid = [(lat, lon) for lat, lon in coords if lat is not None and lon is not None]
        if not valid:
            return None, None
        return (
            sum(lat for lat, _ in valid) / len(valid),
            sum(lon for _, lon in valid) / len(valid),
        )

    async def _filter_properties(
        self,
        *,
        region: str | None,
        city: str | None,
        typology: str | None,
        min_area_m2: float | None = None,
        max_area_m2: float | None = None,
        active_only: bool = True,
    ) -> list[Property]:
        stmt = select(Property)
        if active_only:
            stmt = stmt.where(Property.is_active.is_(True))
        if region:
            stmt = stmt.where(Property.region == region)
        props = list((await self.session.execute(stmt)).scalars().all())
        if city:
            props = [p for p in props if str(p.canonical_attrs.get("city", "")).lower() == city.lower()]
        if typology:
            props = [p for p in props if str(p.canonical_attrs.get("typology", "")).lower() == typology.lower()]
        if min_area_m2 is not None or max_area_m2 is not None:
            filtered: list[Property] = []
            for p in props:
                area = _as_float(p.canonical_attrs.get("area_m2"))
                if area is None:
                    continue
                if min_area_m2 is not None and area < min_area_m2:
                    continue
                if max_area_m2 is not None and area > max_area_m2:
                    continue
                filtered.append(p)
            props = filtered
        return props

    async def _price_cut_rate_30d(self, property_ids: list[uuid.UUID]) -> float | None:
        if not property_ids:
            return None
        cutoff = datetime.now(UTC) - timedelta(days=30)
        events = (
            (
                await self.session.execute(
                    select(PriceEvent)
                    .where(PriceEvent.property_id.in_(property_ids))
                    .where(PriceEvent.event_at >= cutoff)
                    .where(PriceEvent.kind == "price_change")
                    .order_by(PriceEvent.property_id, PriceEvent.event_at)
                )
            )
            .scalars()
            .all()
        )
        if not events:
            return None

        by_prop: dict[uuid.UUID, list[PriceEvent]] = {}
        for e in events:
            by_prop.setdefault(e.property_id, []).append(e)

        cut_props = 0
        considered = 0
        for pid, evs in by_prop.items():
            prior = (
                (
                    await self.session.execute(
                        select(PriceEvent)
                        .where(PriceEvent.property_id == pid)
                        .where(PriceEvent.event_at < cutoff)
                        .order_by(PriceEvent.event_at.desc())
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            prices: list[float] = []
            if prior and prior.price_eur is not None:
                prices.append(float(prior.price_eur))
            for e in evs:
                if e.price_eur is not None:
                    prices.append(float(e.price_eur))
            if len(prices) < 2:
                continue
            considered += 1
            if any(prices[i] < prices[i - 1] for i in range(1, len(prices))):
                cut_props += 1

        if considered == 0:
            return None
        return round(cut_props / considered, 3)

    async def _staleness_components(self, prop: Property) -> dict:
        stored = (prop.canonical_attrs or {}).get("staleness_components")
        if isinstance(stored, dict) and "recency" in stored and "sources" in stored:
            return components_dict({k: float(v) for k, v in stored.items()})

        links = (
            (await self.session.execute(select(PropertyObservation).where(PropertyObservation.property_id == prop.id)))
            .scalars()
            .all()
        )
        observations: list[Observation] = []
        for link in links:
            obs = await self.session.get(Observation, link.observation_id)
            if obs:
                observations.append(obs)
        latest_by_source: dict[str, float] = {}
        for o in sorted(observations, key=lambda x: x.observed_at):
            if o.status != "delisted" and o.price_eur is not None:
                latest_by_source[o.source] = float(o.price_eur)
        recency_days = (datetime.now(UTC) - prop.last_seen.replace(tzinfo=UTC)).days
        ppm2 = price_per_m2(
            float(prop.current_price_eur) if prop.current_price_eur else None,
            prop.canonical_attrs.get("area_m2"),
        )
        _, components = compute_staleness(
            recency_days=recency_days,
            source_count=len(latest_by_source) or 1,
            source_prices=list(latest_by_source.values()),
            price_per_m2=ppm2,
            region_median_m2=None,
        )
        return components_dict(components)

    async def _to_summary(self, prop: Property) -> PropertySummary:
        links = (
            (await self.session.execute(select(PropertyObservation).where(PropertyObservation.property_id == prop.id)))
            .scalars()
            .all()
        )
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


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except TypeError, ValueError:
        return None
