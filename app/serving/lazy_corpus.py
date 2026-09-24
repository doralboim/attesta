"""Fetch and save only the city a search asked for, then notify listeners."""

from __future__ import annotations

import asyncio
import re
import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import async_session_factory
from app.ingestion.base import RawListing
from app.ingestion.idealista_pt import IdealistaPtCollector
from app.ingestion.imovirtual import ImovirtualCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.serving.tools import SearchFilters, ToolService

ListingFetcher = Callable[[SearchFilters], Awaitable[list[RawListing]]]

_GENERIC_REGIONS = frozenset({"", "PT", "PORTUGAL"})


class CorpusFetchError(Exception):
    """Live fetch cannot run for this request."""


def place_slug(name: str) -> str:
    folded = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", folded).strip("-")


def portal_search_urls(city: str) -> tuple[list[str], list[str]]:
    slug = place_slug(city)
    if not slug:
        raise CorpusFetchError("Name a city to fetch listings.")
    idealista = [f"https://www.idealista.pt/comprar-casas/{slug}/"]
    imovirtual = [f"https://www.imovirtual.com/pt/resultados/comprar/apartamento/{slug}/{slug}"]
    return idealista, imovirtual


def bind_requested_place(listing: RawListing, city: str, region: str | None) -> bool:
    """Keep listings for the requested city. Fill a missing city or a generic region."""
    got = str(listing.attrs.get("city") or "").strip()
    if got and got.lower() != city.lower():
        return False
    attrs = dict(listing.attrs)
    if not got:
        attrs["city"] = city
    source_region = str(attrs.get("region") or "").strip()
    if region and source_region.upper() in _GENERIC_REGIONS:
        attrs["region"] = region
    listing.attrs = attrs
    return True


async def fetch_live_listings(filters: SearchFilters) -> list[RawListing]:
    settings = get_settings()
    if not settings.apify_token:
        raise CorpusFetchError("Live fetch is not configured.")
    city = (filters.city or "").strip()
    idealista_urls, imovirtual_urls = portal_search_urls(city)
    listings: list[RawListing] = []
    errors: list[str] = []
    for collector_cls, urls in (
        (IdealistaPtCollector, idealista_urls),
        (ImovirtualCollector, imovirtual_urls),
    ):
        try:
            listings.extend(await collector_cls(search_urls=urls).fetch_listings())
        except Exception as exc:
            errors.append(str(exc))
    if not listings and errors:
        raise CorpusFetchError(errors[0])
    return listings


def _coverage(status: str, message: str, **extra: object) -> dict:
    body: dict = {"status": status, "message": message}
    body.update(extra)
    return body


def _with_coverage(found: dict, status: str, message: str, **extra: object) -> dict:
    return {**found, "coverage": _coverage(status, message, **extra)}


@dataclass
class CorpusJob:
    id: str
    city: str
    message: str
    payload: dict | None = None
    subscribers: list[asyncio.Queue] = field(default_factory=list)
    finished: asyncio.Event = field(default_factory=asyncio.Event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self.subscribers.append(queue)
        if self.payload is not None:
            queue.put_nowait(self.payload)
        return queue

    async def publish(self, event: dict) -> None:
        if "listings" in event:
            self.payload = event
            self.message = str(event.get("coverage", {}).get("message", self.message))
            self.finished.set()
        else:
            self.message = str(event.get("message", self.message))
        for queue in self.subscribers:
            await queue.put(event)


class LazyCorpus:
    def __init__(self) -> None:
        self.jobs: dict[str, CorpusJob] = {}
        self.by_city: dict[str, str] = {}
        self.filled_cities: set[str] = set()
        self.fetcher: ListingFetcher = fetch_live_listings

    def reset(self) -> None:
        self.jobs.clear()
        self.by_city.clear()
        self.filled_cities.clear()
        self.fetcher = fetch_live_listings

    async def begin_search(self, session: AsyncSession, filters: SearchFilters) -> dict:
        tools = ToolService(session)
        found = await tools.search_listings(filters)
        city = (filters.city or "").strip()
        if not city:
            if found["count"]:
                return _with_coverage(found, "ready", "Saved observations match this query.")
            return _with_coverage(
                found,
                "needs_city",
                "Name a city to fetch listings. Attesta only saves the place you ask for.",
            )

        place = await tools.search_listings(
            SearchFilters(city=city, include_inactive=filters.include_inactive, limit=1)
        )
        if place["count"] or city.lower() in self.filled_cities:
            if found["count"]:
                message = "Saved observations match this query."
            else:
                message = "This place is already saved. None of those observations match the other filters."
            return _with_coverage(found, "ready", message)

        existing_id = self.by_city.get(city.lower())
        if existing_id and existing_id in self.jobs and not self.jobs[existing_id].finished.is_set():
            return self._updating_body(self.jobs[existing_id])

        job = CorpusJob(
            id=str(uuid.uuid4()),
            city=city,
            message=f"No saved observations for {city}. Fetching that place now.",
        )
        self.jobs[job.id] = job
        self.by_city[city.lower()] = job.id
        asyncio.create_task(self._run(job, filters))
        return self._updating_body(job)

    def _updating_body(self, job: CorpusJob) -> dict:
        return {
            "count": 0,
            "listings": [],
            "coverage": _coverage(
                "updating",
                job.message,
                job_id=job.id,
                events_url=f"/v1/listings/ingest/{job.id}/events",
            ),
        }

    async def _run(self, job: CorpusJob, filters: SearchFilters) -> None:
        await job.publish({"status": "updating", "message": job.message, "job_id": job.id})
        city = job.city
        try:
            fetched = await self.fetcher(filters)
            async with async_session_factory() as session:
                ingest = IngestionService(session)
                saved_n = 0
                for listing in fetched:
                    if not bind_requested_place(listing, city, filters.region):
                        continue
                    await ingest.ingest_one(listing)
                    saved_n += 1
                await ResolutionService(session).resolve_all()
                found = await ToolService(session).search_listings(filters)
            self.filled_cities.add(city.lower())
            if saved_n and found["count"] == 0:
                message = f"Saved {saved_n} observations for {city}. None match the other filters."
            elif saved_n:
                message = f"Saved {saved_n} observations for {city}."
            else:
                message = f"Fetched {city} and saved no listings."
            payload = _with_coverage(found, "ready", message, job_id=job.id)
        except CorpusFetchError as exc:
            payload = {
                "count": 0,
                "listings": [],
                "coverage": _coverage("unavailable", str(exc), job_id=job.id),
            }
        except Exception:
            payload = {
                "count": 0,
                "listings": [],
                "coverage": _coverage("unavailable", f"Could not fetch {city}.", job_id=job.id),
            }
        await job.publish(payload)


lazy_corpus = LazyCorpus()
