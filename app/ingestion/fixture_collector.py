"""Default collector — bundled JSON fixtures for local dev, CI, and demos."""

import json
from datetime import datetime
from pathlib import Path

from app.ingestion.base import BaseCollector, RawListing

FIXTURES_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "idealista_pt_listings.json"


class FixtureCollector(BaseCollector):
    source_name = "idealista_pt"

    def __init__(self, fixtures_path: Path | None = None) -> None:
        self.fixtures_path = fixtures_path or FIXTURES_PATH

    async def fetch_listings(self) -> list[RawListing]:
        with self.fixtures_path.open() as f:
            data = json.load(f)
        return [_to_raw(item) for item in data]

    async def fetch_listing_by_url(self, url: str) -> RawListing | None:
        listings = await self.fetch_listings()
        for listing in listings:
            if listing.url == url:
                return listing
        return None


def _to_raw(item: dict) -> RawListing:
    return RawListing(
        source=item.get("source", "idealista_pt"),
        source_listing_id=item["source_listing_id"],
        url=item["url"],
        observed_at=datetime.fromisoformat(item["observed_at"]),
        price_eur=item.get("price_eur"),
        status=item.get("status", "active"),
        attrs=item.get("attrs", {}),
        geo_lat=item.get("geo_lat"),
        geo_lon=item.get("geo_lon"),
        raw_payload=item,
    )
