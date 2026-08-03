"""Tool pricing — single source of truth."""

from decimal import Decimal

TOOL_PRICES_EUR: dict[str, Decimal] = {
    "search_listings": Decimal("0.01"),
    "get_property": Decimal("0.01"),
    "get_price_history": Decimal("0.02"),
    "get_market_stats": Decimal("0.02"),
    "get_comps": Decimal("0.02"),
    "check_listing_freshness": Decimal("0.02"),
    "verify_claim_corpus": Decimal("0.02"),
    "verify_claim_deep": Decimal("0.08"),
    "get_evidence": Decimal("0.01"),
}


def price_for_tool(tool: str) -> Decimal:
    return TOOL_PRICES_EUR.get(tool, Decimal("0.01"))
