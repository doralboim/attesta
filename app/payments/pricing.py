"""Tool pricing — defaults plus a DB-backed, cacheable override."""

from __future__ import annotations

import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ToolPrice

DEFAULT_TOOL_PRICES_EUR: dict[str, Decimal] = {
    "search_listings": Decimal("0.01"),
    "get_property": Decimal("0.01"),
    "get_price_history": Decimal("0.02"),
    "get_market_stats": Decimal("0.02"),
    "get_comps": Decimal("0.02"),
    "check_listing_freshness": Decimal("0.02"),
    "verify_claim_corpus": Decimal("0.02"),
    "verify_claim_deep": Decimal("0.08"),
    "verify_url": Decimal("0.08"),
    "get_evidence": Decimal("0.01"),
}

# Backwards-compatible alias used by older imports / docs.
TOOL_PRICES_EUR = DEFAULT_TOOL_PRICES_EUR

_CACHE_TTL_SECONDS = 30.0
_cache: dict[str, tuple[Decimal, float]] = {}


def price_for_tool(tool: str) -> Decimal:
    """Synchronous default lookup — used when no session is available."""
    return DEFAULT_TOOL_PRICES_EUR.get(tool, Decimal("0.01"))


def known_tools() -> frozenset[str]:
    return frozenset(DEFAULT_TOOL_PRICES_EUR)


def invalidate_price_cache(tool: str | None = None) -> None:
    if tool is None:
        _cache.clear()
        return
    _cache.pop(tool, None)


class PricingService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_price(self, tool: str) -> Decimal:
        now = time.monotonic()
        cached = _cache.get(tool)
        if cached and now - cached[1] < _CACHE_TTL_SECONDS:
            return cached[0]

        row = await self.session.get(ToolPrice, tool)
        price = Decimal(str(row.price_eur)) if row else price_for_tool(tool)
        _cache[tool] = (price, now)
        return price

    async def list_prices(self) -> dict[str, str]:
        rows = (await self.session.execute(select(ToolPrice))).scalars().all()
        out = {name: str(amount) for name, amount in DEFAULT_TOOL_PRICES_EUR.items()}
        for row in rows:
            out[row.tool] = str(Decimal(str(row.price_eur)).normalize())
        return out

    async def set_price(self, tool: str, price_eur: Decimal) -> None:
        if tool not in DEFAULT_TOOL_PRICES_EUR:
            msg = f"Unknown tool: {tool}"
            raise ValueError(msg)
        if price_eur < 0:
            msg = "price_eur must be >= 0"
            raise ValueError(msg)

        row = await self.session.get(ToolPrice, tool)
        if row:
            row.price_eur = price_eur
        else:
            self.session.add(ToolPrice(tool=tool, price_eur=price_eur))
        await self.session.commit()
        invalidate_price_cache(tool)
