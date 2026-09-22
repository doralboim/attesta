"""Evidence gathering from corpus (and optional live fetch in deep mode)."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Observation, PropertyObservation, Snapshot
from app.ingestion.pipeline import IngestionService
from app.ingestion.url_dispatch import UnsupportedListingUrlError, resolve_collector_for_url
from app.llm.factory import llm_is_configured
from app.resolution.matcher import ResolutionService
from app.serving.tools import SearchFilters, ToolService
from app.verification.adjudicate import adjudicate_with_llm
from app.verification.evidence import snapshot_hash_ref, snapshot_id_ref
from app.verification.parse import parse_claim

logger = structlog.get_logger()


class EvidenceRetriever:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.tools = ToolService(session)

    async def gather_verdicts(self, claim: str, depth: str = "corpus") -> tuple[list[dict], list[str]]:
        predicates = await parse_claim(claim)
        listing = await self._find_best_listing(predicates, claim)

        if not listing:
            return (
                [
                    {
                        "predicate": "entity_match",
                        "verdict": "UNVERIFIABLE",
                        "evidence": [],
                        "notes": "No matching property in corpus.",
                    }
                ],
                [],
            )

        prop_id = uuid.UUID(listing["id"])
        history = await self.tools.get_price_history(prop_id)
        freshness = await self.tools.check_listing_freshness(prop_id)

        if depth == "deep":
            await self._refresh_listing_from_source(prop_id)
            refreshed = await self.tools.get_property(prop_id)
            if refreshed:
                listing = refreshed

        evidence_bundle = await self._build_evidence_bundle(
            claim=claim,
            listing=listing,
            predicates=predicates,
            history=history,
            freshness=freshness,
            prop_id=prop_id,
        )

        if llm_is_configured():
            verdicts = await adjudicate_with_llm(claim, predicates, evidence_bundle)
        else:
            verdicts, _ = await self._adjudicate_deterministic(claim, predicates, listing, history, freshness, prop_id)
        verdicts = await self._annotate_source_classes(verdicts)
        all_evidence = _collect_evidence_refs(verdicts)
        return verdicts, all_evidence

    async def gather_verdicts_for_url(self, url: str) -> tuple[list[dict], list[str]]:
        """Fetch one listing URL, ingest, resolve, and issue a single-source receipt."""
        try:
            collector = resolve_collector_for_url(url)
        except UnsupportedListingUrlError as exc:
            return (
                [
                    {
                        "predicate": "url",
                        "verdict": "UNVERIFIABLE",
                        "evidence": [],
                        "source_classes": [],
                        "notes": str(exc),
                    }
                ],
                [],
            )

        listing = await collector.fetch_listing_by_url(url)
        if listing is None:
            return (
                [
                    {
                        "predicate": "url",
                        "verdict": "UNVERIFIABLE",
                        "evidence": [],
                        "source_classes": [],
                        "notes": "Source returned no listing for this URL.",
                    }
                ],
                [],
            )

        ingest = IngestionService(self.session)
        obs = await ingest.ingest_one(listing)
        await ResolutionService(self.session).resolve_all()

        snap = await self.session.get(Snapshot, obs.snapshot_id)
        evidence = [snapshot_hash_ref(snap.content_hash)] if snap else []
        source_class = obs.source_class or "portal"

        verdicts: list[dict] = []
        if obs.price_eur is not None:
            verdicts.append(
                {
                    "predicate": f"price={float(obs.price_eur)}",
                    "verdict": "CORROBORATED",
                    "evidence": evidence,
                    "sources": 1,
                    "source_classes": [source_class],
                    "notes": "Single-source observation from the supplied URL.",
                }
            )
        status = (obs.status or "").lower()
        if status:
            label = "CORROBORATED" if status != "delisted" else "CONTRADICTED"
            verdicts.append(
                {
                    "predicate": "availability",
                    "verdict": label,
                    "evidence": evidence,
                    "sources": 1,
                    "source_classes": [source_class],
                    "notes": f"Observed status={obs.status} at URL.",
                }
            )
        if not verdicts:
            verdicts.append(
                {
                    "predicate": "url",
                    "verdict": "UNVERIFIABLE",
                    "evidence": evidence,
                    "source_classes": [source_class],
                    "notes": "Fetched listing had no price or status to adjudicate.",
                }
            )
        return verdicts, _collect_evidence_refs(verdicts)

    async def _adjudicate_deterministic(
        self,
        claim: str,
        predicates: dict,
        listing: dict,
        history: dict | None,
        freshness: dict | None,
        prop_id: uuid.UUID,
    ) -> tuple[list[dict], list[str]]:
        verdicts: list[dict] = []
        all_evidence: list[str] = []

        if "price" in predicates:
            price = listing.get("current_price_eur")
            claimed = predicates["price"]
            delta = abs((price or 0) - claimed) / max(claimed, 1)
            label = "CORROBORATED" if delta <= 0.03 else "CONTRADICTED"
            evidence = await self._snapshot_evidence_for_property(prop_id, history)
            verdicts.append(
                {
                    "predicate": f"price={claimed}",
                    "verdict": label,
                    "evidence": evidence,
                    "sources": len(listing.get("sources", [])),
                }
            )
            all_evidence.extend(evidence)

        if "days_on_market" in predicates:
            claimed_dom = predicates["days_on_market"]
            dom = listing.get("days_on_market", 0)
            label = "CORROBORATED" if abs(dom - claimed_dom) <= 7 else "CONTRADICTED"
            evidence = await self._snapshot_evidence_for_property(prop_id, history)
            verdicts.append(
                {
                    "predicate": f"days_on_market={claimed_dom}",
                    "verdict": label,
                    "evidence": evidence,
                    "sources": 1,
                }
            )
            all_evidence.extend(evidence)

        if predicates.get("availability") or "listed" in claim.lower():
            evidence = await self._snapshot_evidence_for_property(prop_id, history)
            if freshness and not freshness.get("is_active"):
                verdicts.append(
                    {
                        "predicate": "availability",
                        "verdict": "CONTRADICTED",
                        "evidence": evidence,
                        "notes": "Property delisted or stale in corpus.",
                    }
                )
            else:
                verdicts.append(
                    {
                        "predicate": "availability",
                        "verdict": "CORROBORATED",
                        "evidence": evidence,
                        "notes": "Active across tracked sources.",
                    }
                )
            all_evidence.extend(evidence)

        return verdicts, list(dict.fromkeys(all_evidence))

    async def _build_evidence_bundle(
        self,
        *,
        claim: str,
        listing: dict,
        predicates: dict,
        history: dict | None,
        freshness: dict | None,
        prop_id: uuid.UUID,
    ) -> dict:
        evidence_refs = await self._snapshot_evidence_for_property(prop_id, history)
        snapshots: list[dict] = []
        for ref in evidence_refs:
            kind, value = ref.split(":", 1) if ":" in ref else ("opaque", ref)
            if kind == "sha256":
                snap = await self.session.scalar(select(Snapshot).where(Snapshot.content_hash == value).limit(1))
            elif ref.startswith("snap:"):
                snap = await self.session.get(Snapshot, int(ref.removeprefix("snap:")))
            else:
                snap = None
            if snap:
                obs = await self.session.scalar(select(Observation).where(Observation.snapshot_id == snap.id).limit(1))
                snapshots.append(
                    {
                        "ref": ref,
                        "source": snap.source,
                        "url": snap.url,
                        "fetched_at": snap.fetched_at.isoformat(),
                        "content_hash": snap.content_hash,
                        "price_eur": float(obs.price_eur) if obs and obs.price_eur else None,
                        "status": obs.status if obs else None,
                        "source_class": obs.source_class if obs else "portal",
                    }
                )

        return {
            "claim": claim,
            "predicates": predicates,
            "listing": listing,
            "freshness": freshness,
            "history_event_count": len(history.get("events", [])) if history else 0,
            "snapshots": snapshots,
            "evidence_refs": evidence_refs,
        }

    async def _find_best_listing(self, predicates: dict, claim: str) -> dict | None:
        include_inactive = bool(predicates.get("availability"))
        base = SearchFilters(
            city=predicates.get("city"),
            typology=predicates.get("typology"),
            region=predicates.get("region"),
            include_inactive=include_inactive,
            limit=5,
        )

        if "price" in predicates:
            tight = SearchFilters(
                city=base.city,
                typology=base.typology,
                region=base.region,
                min_price_eur=predicates.get("price_min"),
                max_price_eur=predicates.get("price_max"),
                include_inactive=include_inactive,
                limit=5,
            )
            listings = (await self.tools.search_listings(tight))["listings"]
            if listings:
                return listings[0]

        listings = (await self.tools.search_listings(base))["listings"]
        if listings:
            if "price" not in predicates:
                return listings[0]
            claimed = predicates["price"]
            return min(
                listings,
                key=lambda row: abs((row.get("current_price_eur") or 0) - claimed),
            )

        if predicates.get("city"):
            city_only = SearchFilters(
                city=predicates["city"],
                include_inactive=include_inactive,
                limit=5,
            )
            listings = (await self.tools.search_listings(city_only))["listings"]
            if listings:
                if "price" not in predicates:
                    return listings[0]
                claimed = predicates["price"]
                return min(
                    listings,
                    key=lambda row: abs((row.get("current_price_eur") or 0) - claimed),
                )

        return None

    async def _snapshot_evidence_for_property(self, prop_id: uuid.UUID, history: dict | None) -> list[str]:
        refs: list[str] = []
        if history and history.get("events"):
            for event in history["events"]:
                sid = event.get("snapshot_id")
                if sid:
                    snap = await self.session.get(Snapshot, int(sid))
                    if snap:
                        refs.append(snapshot_hash_ref(snap.content_hash))
                    else:
                        refs.append(snapshot_id_ref(int(sid)))

        if not refs:
            links = (
                (
                    await self.session.execute(
                        select(PropertyObservation).where(PropertyObservation.property_id == prop_id)
                    )
                )
                .scalars()
                .all()
            )
            for link in links:
                obs = await self.session.get(Observation, link.observation_id)
                if obs:
                    snap = await self.session.get(Snapshot, obs.snapshot_id)
                    if snap:
                        refs.append(snapshot_hash_ref(snap.content_hash))

        return refs or [f"property:{prop_id}"]

    async def _refresh_listing_from_source(self, prop_id: uuid.UUID) -> None:
        """Re-fetch the matched property's last-known source URL. Fail soft."""
        url = await self._latest_source_url(prop_id)
        if not url:
            logger.info("deep_refresh_skipped", property_id=str(prop_id), reason="no_source_url")
            return
        try:
            collector = resolve_collector_for_url(url)
            listing = await collector.fetch_listing_by_url(url)
            if listing is None:
                logger.info("deep_refresh_empty", property_id=str(prop_id), url=url)
                return
            await IngestionService(self.session).ingest_one(listing)
            await ResolutionService(self.session).resolve_all()
        except Exception:
            logger.exception("deep_refresh_failed", property_id=str(prop_id), url=url)

    async def _latest_source_url(self, prop_id: uuid.UUID) -> str | None:
        links = (
            (await self.session.execute(select(PropertyObservation).where(PropertyObservation.property_id == prop_id)))
            .scalars()
            .all()
        )
        if not links:
            return None
        obs_ids = [link.observation_id for link in links]
        obs = (
            (
                await self.session.execute(
                    select(Observation)
                    .where(Observation.id.in_(obs_ids))
                    .order_by(Observation.observed_at.desc())
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        if not obs:
            return None
        snap = await self.session.get(Snapshot, obs.snapshot_id)
        return snap.url if snap else None

    async def _annotate_source_classes(self, verdicts: list[dict]) -> list[dict]:
        annotated: list[dict] = []
        for verdict in verdicts:
            v = dict(verdict)
            refs = list(v.get("evidence") or [])
            v["source_classes"] = await self._source_classes_for_refs(refs)
            annotated.append(v)
        return annotated

    async def _source_classes_for_refs(self, refs: list[str]) -> list[str]:
        classes: list[str] = []
        seen: set[str] = set()
        for ref in refs:
            kind, value = ref.split(":", 1) if ":" in ref else ("opaque", ref)
            snap = None
            if kind == "sha256":
                snap = await self.session.scalar(select(Snapshot).where(Snapshot.content_hash == value).limit(1))
            elif ref.startswith("snap:"):
                try:
                    snap = await self.session.get(Snapshot, int(ref.removeprefix("snap:")))
                except ValueError:
                    snap = None
            if not snap:
                continue
            obs = await self.session.scalar(select(Observation).where(Observation.snapshot_id == snap.id).limit(1))
            source_class = (obs.source_class if obs else None) or "portal"
            if source_class not in seen:
                seen.add(source_class)
                classes.append(source_class)
        return classes


def _collect_evidence_refs(verdicts: list[dict]) -> list[str]:
    seen: set[str] = set()
    refs: list[str] = []
    for verdict in verdicts:
        for ref in verdict.get("evidence") or []:
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    return refs
