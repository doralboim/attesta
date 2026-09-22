"""Build Apify actor input payloads for configured portal collectors."""

from __future__ import annotations


def parse_search_urls(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def idealista_actor_input(search_urls: list[str], max_results: int) -> dict:
    """Input for dz_omar/idealista-scraper-api."""
    return {
        "Property_urls": [{"url": url} for url in search_urls],
        "desiredResults": max_results,
        "detailMode": False,
    }


def imovirtual_actor_input(search_urls: list[str], max_results: int) -> dict:
    """Input for automation-lab/imovirtual-scraper."""
    return {
        "startUrls": search_urls,
        "maxItems": max_results,
    }
