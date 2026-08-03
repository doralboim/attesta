"""MCP server — tools sharing implementations with REST."""

from __future__ import annotations

import uuid

from fastmcp import FastMCP

from app.db.session import async_session_factory
from app.payments.metering import MeteringService
from app.serving import descriptions as desc
from app.serving.tools import CompsFilters, MarketStatsFilters, SearchFilters, ToolService
from app.verification.pipeline import VerificationPipeline

mcp = FastMCP(
    "attesta",
    instructions=(
        "Attesta: provenance-grade Portugal residential property data and signed verification. "
        "Authenticate with API key in MCP session metadata or pay per call via x402."
    ),
)


async def _metered(tool: str, api_key: str | None = None, payment: str | None = None):
    async with async_session_factory() as session:
        metering = MeteringService(session)
        return await metering.authorize(tool, api_key=api_key, payment_header=payment)


@mcp.tool(name="search_listings", description=desc.SEARCH_LISTINGS)
async def search_listings(
    region: str | None = None,
    city: str | None = None,
    min_price_eur: float | None = None,
    max_price_eur: float | None = None,
    limit: int = 20,
    api_key: str | None = None,
) -> dict:
    await _metered("search_listings", api_key=api_key)
    async with async_session_factory() as session:
        return await ToolService(session).search_listings(
            SearchFilters(
                region=region,
                city=city,
                min_price_eur=min_price_eur,
                max_price_eur=max_price_eur,
                limit=limit,
            )
        )


@mcp.tool(name="get_property", description=desc.GET_PROPERTY)
async def get_property(property_id: str, api_key: str | None = None) -> dict:
    await _metered("get_property", api_key=api_key)
    async with async_session_factory() as session:
        result = await ToolService(session).get_property(uuid.UUID(property_id))
        return result or {"error": "not_found"}


@mcp.tool(name="get_price_history", description=desc.GET_PRICE_HISTORY)
async def get_price_history(property_id: str, api_key: str | None = None) -> dict:
    await _metered("get_price_history", api_key=api_key)
    async with async_session_factory() as session:
        result = await ToolService(session).get_price_history(uuid.UUID(property_id))
        return result or {"error": "not_found"}


@mcp.tool(name="get_market_stats", description=desc.GET_MARKET_STATS)
async def get_market_stats(
    region: str | None = None,
    city: str | None = None,
    typology: str | None = None,
    min_area_m2: float | None = None,
    max_area_m2: float | None = None,
    api_key: str | None = None,
) -> dict:
    await _metered("get_market_stats", api_key=api_key)
    async with async_session_factory() as session:
        return await ToolService(session).get_market_stats(
            MarketStatsFilters(
                region=region,
                city=city,
                typology=typology,
                min_area_m2=min_area_m2,
                max_area_m2=max_area_m2,
            )
        )


@mcp.tool(name="get_comps", description=desc.GET_COMPS)
async def get_comps(
    region: str,
    area_m2: float,
    city: str | None = None,
    typology: str | None = None,
    area_tolerance_pct: float = 15.0,
    geo_radius_m: float | None = None,
    property_id: str | None = None,
    limit: int = 20,
    api_key: str | None = None,
) -> dict:
    await _metered("get_comps", api_key=api_key)
    async with async_session_factory() as session:
        return await ToolService(session).get_comps(
            CompsFilters(
                region=region,
                city=city,
                typology=typology,
                area_m2=area_m2,
                area_tolerance_pct=area_tolerance_pct,
                geo_radius_m=geo_radius_m,
                property_id=uuid.UUID(property_id) if property_id else None,
                limit=limit,
            )
        )


@mcp.tool(name="check_listing_freshness", description=desc.CHECK_LISTING_FRESHNESS)
async def check_listing_freshness(property_id: str, api_key: str | None = None) -> dict:
    await _metered("check_listing_freshness", api_key=api_key)
    async with async_session_factory() as session:
        result = await ToolService(session).check_listing_freshness(uuid.UUID(property_id))
        return result or {"error": "not_found"}


@mcp.tool(name="verify_claim", description=desc.VERIFY_CLAIM)
async def verify_claim(claim: str, depth: str = "corpus", api_key: str | None = None) -> dict:
    tool = "verify_claim_deep" if depth == "deep" else "verify_claim_corpus"
    ctx = await _metered(tool, api_key=api_key)
    async with async_session_factory() as session:
        return await VerificationPipeline(session).verify(
            claim,
            depth=depth,
            usage_event_id=ctx.usage_event_id,
        )
