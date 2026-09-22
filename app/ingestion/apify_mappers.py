"""Map Apify actor dataset rows to Attesta RawListing records."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.ingestion.base import RawListing


def _first_str(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _nested(obj: dict[str, Any], *keys: str) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def idealista_item_to_raw(item: dict[str, Any]) -> RawListing | None:
    """Map dz_omar/idealista-scraper-api (and similar) output to RawListing."""
    listing_id = _first_str(
        item.get("propertyId"),
        item.get("adid"),
        item.get("propertyCode"),
    )
    url = _first_str(item.get("url"), item.get("detailWebLink"), item.get("originalUrl"), item.get("sourceUrl"))
    if not listing_id or not url:
        return None

    price_raw = item.get("price")
    if price_raw is None:
        price_raw = _nested(item, "priceInfo", "amount")
    price_eur = float(price_raw) if price_raw is not None else None

    typology = _first_str(
        _nested(item, "detailedType", "typology"),
        item.get("propertyType"),
        item.get("extendedPropertyType"),
    )
    area = _nested(item, "moreCharacteristics", "constructedArea")
    if area is None:
        area = item.get("size")

    city = _first_str(
        _nested(item, "ubication", "locationName"),
        item.get("municipality"),
        item.get("district"),
        item.get("province"),
    )

    lat = item.get("latitude")
    if lat is None:
        lat = _nested(item, "ubication", "latitude")
    lon = item.get("longitude")
    if lon is None:
        lon = _nested(item, "ubication", "longitude")

    suggested = item.get("suggestedTexts")
    title = suggested.get("title") if isinstance(suggested, dict) else item.get("title")

    return RawListing(
        source="idealista_pt",
        source_listing_id=listing_id,
        url=url,
        observed_at=datetime.now(UTC),
        price_eur=price_eur,
        status=_first_str(item.get("status"), item.get("state"), "active") or "active",
        attrs={
            "typology": typology or None,
            "area_m2": float(area) if area is not None else None,
            "city": city or None,
            "title": title,
            "region": item.get("country") or "PT",
        },
        geo_lat=float(lat) if lat is not None else None,
        geo_lon=float(lon) if lon is not None else None,
        raw_payload=item,
    )


def imovirtual_item_to_raw(item: dict[str, Any]) -> RawListing | None:
    """Map automation-lab/imovirtual-scraper output to RawListing."""
    listing_id = _first_str(item.get("listingId"), item.get("id"))
    url = _first_str(item.get("url"))
    if not listing_id or not url:
        return None

    rooms = _first_str(item.get("rooms"))
    typology = f"T{rooms}" if rooms and rooms.isdigit() else rooms or item.get("estate")

    return RawListing(
        source="imovirtual",
        source_listing_id=listing_id,
        url=url,
        observed_at=datetime.now(UTC),
        price_eur=float(item["price"]) if item.get("price") is not None else None,
        status="active",
        attrs={
            "typology": typology or None,
            "area_m2": float(item["areaM2"]) if item.get("areaM2") is not None else None,
            "city": item.get("city") or item.get("district"),
            "title": item.get("title"),
            "transaction": item.get("transaction"),
        },
        geo_lat=None,
        geo_lon=None,
        raw_payload=item,
    )


def map_actor_items(source: str, items: list[dict[str, Any]]) -> list[RawListing]:
    mapper = idealista_item_to_raw if source == "idealista_pt" else imovirtual_item_to_raw
    listings: list[RawListing] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        mapped = mapper(item)
        if mapped is not None:
            listings.append(mapped)
    return listings
