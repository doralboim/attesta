"""Versioned response envelopes for market-data tools (schema_version 1.0)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "1.0"
DEFAULT_CURRENCY = "EUR"
SUPPORTED_MARKETS = frozenset({"PT"})


def as_of_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def market_from_region(region: str | None) -> str | None:
    """Return supported market code, or None if unsupported / unknown."""
    if region is None or region == "":
        return "PT"
    upper = region.strip().upper()
    if upper == "PT" or upper.startswith("PT-") or upper.startswith("PT_"):
        return "PT"
    # Explicit non-PT codes (e.g. GR-*) → unsupported
    if len(upper) >= 2 and upper[:2].isalpha() and upper[:2] != "PT":
        return None
    return "PT"


def market_envelope(
    data: dict[str, Any] | None,
    *,
    coverage: dict[str, Any],
    limitations: list[str] | None = None,
    currency: str = DEFAULT_CURRENCY,
    as_of: str | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of or as_of_now(),
        "currency": currency,
        "coverage": coverage,
        "limitations": list(limitations or []),
        "data": data,
    }


def unsupported_market_envelope(
    *,
    region: str | None = None,
    city: str | None = None,
    asset_type: str = "residential_ask",
) -> dict[str, Any]:
    coverage: dict[str, Any] = {
        "market": region.split("-")[0].upper() if region else "unknown",
        "asset_type": asset_type,
    }
    if region:
        coverage["region"] = region
    if city:
        coverage["city"] = city
    return market_envelope(
        None,
        coverage=coverage,
        limitations=["unsupported_market"],
    )
