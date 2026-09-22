"""Map a listing URL to a collector. Live actors only when APIFY_TOKEN is set."""

from __future__ import annotations

from urllib.parse import urlparse

from app.config import get_settings
from app.ingestion.base import BaseCollector
from app.ingestion.fixture_collector import FixtureCollector


class UnsupportedListingUrlError(ValueError):
    """Listing host is not a known portal."""


def resolve_collector_for_url(url: str) -> BaseCollector:
    host = (urlparse(url).netloc or "").lower()
    settings = get_settings()
    live = bool(settings.apify_token)

    if "idealista" in host:
        if live:
            from app.ingestion.idealista_pt import IdealistaPtCollector

            return IdealistaPtCollector()
        return FixtureCollector()
    if "imovirtual" in host:
        if live:
            from app.ingestion.imovirtual import ImovirtualCollector

            return ImovirtualCollector()
        return FixtureCollector()

    msg = f"Unsupported listing URL host: {host or '(empty)'}"
    raise UnsupportedListingUrlError(msg)
