"""Generic collector interface — source #2 is a subclass, not a refactor."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class RawListing:
    source: str
    source_listing_id: str
    url: str
    observed_at: datetime
    price_eur: float | None
    status: str
    attrs: dict
    geo_lat: float | None = None
    geo_lon: float | None = None
    raw_payload: dict | None = None
    source_class: str = "portal"


class BaseCollector(ABC):
    source_name: str

    @abstractmethod
    async def fetch_listings(self) -> list[RawListing]:
        """Fetch current listings from the source."""

    @abstractmethod
    async def fetch_listing_by_url(self, url: str) -> RawListing | None:
        """Live re-fetch for verify_claim deep mode."""
