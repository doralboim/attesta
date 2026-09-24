"""Imovirtual Portugal live collector (Apify: automation-lab/imovirtual-scraper)."""

import httpx

from app.config import get_settings
from app.ingestion.apify import run_apify_actor
from app.ingestion.apify_inputs import imovirtual_actor_input, parse_search_urls
from app.ingestion.apify_mappers import map_actor_items
from app.ingestion.base import BaseCollector, RawListing

DEFAULT_IMOVIRTUAL_SEARCH_URLS = (
    "https://www.imovirtual.com/pt/resultados/comprar/apartamento/faro/faro,"
    "https://www.imovirtual.com/pt/resultados/comprar/apartamento/lisboa/lisboa"
)


class ImovirtualCollector(BaseCollector):
    source_name = "imovirtual"

    def __init__(self, search_urls: list[str] | None = None) -> None:
        settings = get_settings()
        if not settings.apify_token or not settings.apify_imovirtual_actor_id:
            raise ValueError(
                "APIFY_TOKEN and APIFY_IMOVIRTUAL_ACTOR_ID required for live Imovirtual ingestion. "
                "Use attesta-ingest --fixture for local dev."
            )
        self.token = settings.apify_token
        self.actor_id = settings.apify_imovirtual_actor_id
        if search_urls is not None:
            self.search_urls = [url.strip() for url in search_urls if url.strip()]
        else:
            urls_raw = settings.apify_imovirtual_search_urls or DEFAULT_IMOVIRTUAL_SEARCH_URLS
            self.search_urls = parse_search_urls(urls_raw)
        if not self.search_urls:
            msg = "APIFY_IMOVIRTUAL_SEARCH_URLS must contain at least one Imovirtual search URL"
            raise ValueError(msg)
        self.max_results = settings.apify_max_results_per_run

    async def fetch_listings(self) -> list[RawListing]:
        actor_input = imovirtual_actor_input(self.search_urls, self.max_results)
        async with httpx.AsyncClient(timeout=120.0) as client:
            items = await run_apify_actor(client, self.token, self.actor_id, actor_input)
            return map_actor_items(self.source_name, items)

    async def fetch_listing_by_url(self, url: str) -> RawListing | None:
        actor_input = imovirtual_actor_input([url], max_results=1)
        async with httpx.AsyncClient(timeout=120.0) as client:
            items = await run_apify_actor(client, self.token, self.actor_id, actor_input)
            listings = map_actor_items(self.source_name, items)
            return next((listing for listing in listings if listing.url == url), listings[0] if listings else None)
