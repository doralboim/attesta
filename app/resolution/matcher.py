"""Property resolution: cross-portal matching and derived fields."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Observation, PriceEvent, Property, PropertyObservation
from app.resolution.embeddings import cosine_similarity
from app.resolution.staleness import compute_staleness, price_per_m2


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt


def _attrs_match(a: dict, b: dict, tolerance_m2: float = 5.0) -> float:
    """Deterministic attribute agreement score 0..1."""
    score = 0.0
    checks = 0
    for key in ("city", "typology"):
        if a.get(key) and b.get(key):
            checks += 1
            if str(a[key]).lower() == str(b[key]).lower():
                score += 1
    area_a = a.get("area_m2")
    area_b = b.get("area_m2")
    if area_a and area_b:
        checks += 1
        if abs(float(area_a) - float(area_b)) <= tolerance_m2:
            score += 1
    return score / checks if checks else 0.0


def geo_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Haversine approximation in kilometres."""
    from math import asin, cos, radians, sin, sqrt

    r = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


# Back-compat alias
_geo_distance_km = geo_distance_km


class ResolutionService:
    MATCH_THRESHOLD = 0.75
    GEO_BLOCK_KM = 0.5
    EMBEDDING_WEIGHT = 0.25

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve_all(self) -> int:
        """Match unlinked observations to properties."""
        result = await self.session.execute(
            select(Observation).where(~Observation.id.in_(select(PropertyObservation.observation_id)))
        )
        observations = list(result.scalars().all())
        linked = 0
        for obs in observations:
            prop = await self._find_or_create_property(obs)
            self.session.add(
                PropertyObservation(
                    property_id=prop.id,
                    observation_id=obs.id,
                    match_confidence=await self._match_confidence(prop, obs),
                )
            )
            await self._update_derived_fields(prop)
            linked += 1
        await self.session.commit()
        return linked

    async def _find_or_create_property(self, obs: Observation) -> Property:
        candidates = await self._candidate_properties(obs)
        best: Property | None = None
        best_score = 0.0
        for prop in candidates:
            score = await self._match_confidence(prop, obs)
            if score > best_score:
                best_score = score
                best = prop
        if best and best_score >= self.MATCH_THRESHOLD:
            best.consecutive_ingest_misses = 0
            return best

        region = obs.attrs.get("region", obs.attrs.get("city", "PT-UNKNOWN"))
        prop = Property(
            id=uuid.uuid4(),
            canonical_attrs={
                **obs.attrs,
                "geo_lat": obs.geo_lat,
                "geo_lon": obs.geo_lon,
            },
            region=str(region),
            first_seen=obs.observed_at,
            last_seen=obs.observed_at,
            is_active=obs.status != "delisted",
            current_price_eur=float(obs.price_eur) if obs.price_eur else None,
            days_on_market=0,
            staleness_score=0.0,
            consecutive_ingest_misses=0,
        )
        self.session.add(prop)
        await self.session.flush()
        return prop

    async def _candidate_properties(self, obs: Observation) -> list[Property]:
        """Block candidates by city/typology before scoring."""
        props = (await self.session.execute(select(Property))).scalars().all()
        city = str(obs.attrs.get("city", "")).lower()
        typology = str(obs.attrs.get("typology", "")).lower()
        blocked: list[Property] = []
        for prop in props:
            pcity = str(prop.canonical_attrs.get("city", "")).lower()
            ptyp = str(prop.canonical_attrs.get("typology", "")).lower()
            if city and pcity and city != pcity:
                continue
            if typology and ptyp and typology != ptyp:
                continue
            blocked.append(prop)
        return blocked or props

    async def _match_confidence(self, prop: Property, obs: Observation) -> float:
        attr_score = _attrs_match(prop.canonical_attrs, obs.attrs)
        geo_score = 0.0
        plat = prop.canonical_attrs.get("geo_lat")
        plon = prop.canonical_attrs.get("geo_lon")
        if plat and plon and obs.geo_lat and obs.geo_lon:
            dist = geo_distance_km(float(plat), float(plon), obs.geo_lat, obs.geo_lon)
            if dist > self.GEO_BLOCK_KM * 10:
                return 0.0
            geo_score = 1.0 if dist <= self.GEO_BLOCK_KM else max(0, 1 - dist / 5)

        embed_score = 0.0
        if obs.embedding is not None:
            prop_obs = await self._latest_linked_observation(prop.id)
            if prop_obs and prop_obs.embedding is not None:
                embed_score = max(0.0, cosine_similarity(list(obs.embedding), list(prop_obs.embedding)))

        base = 0.45 * attr_score + 0.30 * geo_score
        return min(1.0, base + self.EMBEDDING_WEIGHT * embed_score)

    async def _latest_linked_observation(self, property_id: uuid.UUID) -> Observation | None:
        links = (
            (
                await self.session.execute(
                    select(PropertyObservation).where(PropertyObservation.property_id == property_id)
                )
            )
            .scalars()
            .all()
        )
        if not links:
            return None
        obs_ids = [link.observation_id for link in links]
        return (
            (
                await self.session.execute(
                    select(Observation).where(Observation.id.in_(obs_ids)).order_by(Observation.observed_at.desc())
                )
            )
            .scalars()
            .first()
        )

    async def _update_derived_fields(self, prop: Property) -> None:
        links = (
            (await self.session.execute(select(PropertyObservation).where(PropertyObservation.property_id == prop.id)))
            .scalars()
            .all()
        )
        obs_ids = [link.observation_id for link in links]
        if not obs_ids:
            return
        observations = (
            (await self.session.execute(select(Observation).where(Observation.id.in_(obs_ids)))).scalars().all()
        )

        prop.last_seen = max(_utc(o.observed_at) for o in observations)
        prop.first_seen = min(_utc(o.observed_at) for o in observations)
        active = [o for o in observations if o.status != "delisted"]
        prop.is_active = len(active) > 0
        if active:
            prop.current_price_eur = float(active[-1].price_eur) if active[-1].price_eur else None
        prop.days_on_market = (datetime.now(UTC) - _utc(prop.first_seen)).days
        source_prices = [float(o.price_eur) for o in observations if o.status != "delisted" and o.price_eur is not None]
        # Latest price per source for disagreement
        latest_by_source: dict[str, float] = {}
        for o in sorted(observations, key=lambda x: _utc(x.observed_at)):
            if o.status != "delisted" and o.price_eur is not None:
                latest_by_source[o.source] = float(o.price_eur)
        sources = len(latest_by_source) or len({o.source for o in observations})
        recency_days = (datetime.now(UTC) - _utc(prop.last_seen)).days
        area = prop.canonical_attrs.get("area_m2")
        ppm2 = price_per_m2(prop.current_price_eur, area)
        region_median = await self._region_median_m2(prop.region, exclude_id=prop.id)
        score, components = compute_staleness(
            recency_days=recency_days,
            source_count=sources,
            source_prices=list(latest_by_source.values()) or source_prices,
            price_per_m2=ppm2,
            region_median_m2=region_median,
        )
        prop.staleness_score = score
        # Persist components for API reads without recomputing priors
        attrs = dict(prop.canonical_attrs or {})
        attrs["staleness_components"] = components
        prop.canonical_attrs = attrs

        await self._emit_price_events(prop, observations)

    async def _region_median_m2(self, region: str, *, exclude_id: uuid.UUID | None = None) -> float | None:
        """Cheap region prior: median €/m² of other active listings in region."""
        from statistics import median

        stmt = select(Property).where(Property.region == region).where(Property.is_active.is_(True))
        props = (await self.session.execute(stmt)).scalars().all()
        values: list[float] = []
        for p in props:
            if exclude_id and p.id == exclude_id:
                continue
            price = float(p.current_price_eur) if p.current_price_eur else None
            ppm2 = price_per_m2(price, p.canonical_attrs.get("area_m2"))
            if ppm2 is not None:
                values.append(ppm2)
        if len(values) < 2:
            return None
        return float(median(values))

    async def _emit_price_events(self, prop: Property, observations: list[Observation]) -> None:
        sorted_obs = sorted(observations, key=lambda o: o.observed_at)
        prev_price: float | None = None
        for obs in sorted_obs:
            price = float(obs.price_eur) if obs.price_eur else None
            kind = "listed"
            if obs.status == "delisted":
                kind = "delisted"
            elif prev_price is not None and price is not None and price != prev_price:
                kind = "price_change"
            self.session.add(
                PriceEvent(
                    property_id=prop.id,
                    event_at=obs.observed_at,
                    kind=kind,
                    price_eur=price,
                    source=obs.source,
                    snapshot_id=obs.snapshot_id,
                )
            )
            prev_price = price
