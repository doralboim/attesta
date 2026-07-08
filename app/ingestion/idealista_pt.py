"""Idealista Portugal live collector (optional Apify actor plugin)."""

from datetime import UTC, datetime

import httpx

from app.config import get_settings
from app.ingestion.apify import poll_apify_dataset
from app.ingestion.base import BaseCollector, RawListing


class IdealistaPtCollector(BaseCollector):
    source_name = "idealista_pt"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.apify_token or not settings.apify_idealista_actor_id:
            raise ValueError(
                "APIFY_TOKEN and APIFY_IDEALISTA_ACTOR_ID required for live Idealista ingestion. "
                "Use attesta-ingest --fixture for local dev."
            )
        self.token = settings.apify_token
        self.actor_id = settings.apify_idealista_actor_id

    async def fetch_listings(self) -> list[RawListing]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            items = await poll_apify_dataset(client, self.token, self.actor_id)
            return [_apify_item_to_raw(i) for i in items]

    async def fetch_listing_by_url(self, url: str) -> RawListing | None:
        listings = await self.fetch_listings()
        return next((listing for listing in listings if listing.url == url), None)


def _apify_item_to_raw(item: dict) -> RawListing:
    return RawListing(
        source="idealista_pt",
        source_listing_id=str(item.get("id", item.get("listingId", ""))),
        url=item.get("url", ""),
        observed_at=datetime.now(UTC),
        price_eur=float(item["price"]) if item.get("price") else None,
        status="active",
        attrs={
            "typology": item.get("typology"),
            "area_m2": item.get("area"),
            "city": item.get("city"),
            "title": item.get("title"),
        },
        geo_lat=item.get("latitude"),
        geo_lon=item.get("longitude"),
        raw_payload=item,
    )
