"""Market stats €/m² aggregation and envelope contract."""

from pathlib import Path

import pytest
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.resolution.staleness import price_per_m2
from app.serving.aggregates import euro_m2_stats
from app.serving.envelope import market_from_region
from app.serving.tools import MarketStatsFilters, ToolService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def test_price_per_m2_excludes_missing_area() -> None:
    assert price_per_m2(250000, None) is None
    assert price_per_m2(250000, 0) is None
    assert price_per_m2(None, 80) is None
    assert price_per_m2(240000, 80) == 3000.0


def test_euro_m2_stats_percentiles() -> None:
    stats = euro_m2_stats([2000, 3000, 4000, 5000])
    assert stats["sample_size"] == 4
    assert stats["median_price_per_m2"] == 3500.0
    assert stats["p25_price_per_m2"] is not None
    assert stats["p75_price_per_m2"] is not None
    assert stats["p25_price_per_m2"] < stats["p75_price_per_m2"]


def test_unsupported_market_detection() -> None:
    assert market_from_region("PT-08") == "PT"
    assert market_from_region("GR-I") is None
    assert market_from_region(None) == "PT"


@pytest.mark.asyncio
async def test_get_market_stats_envelope_and_m2(db_session: AsyncSession) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    result = await ToolService(db_session).get_market_stats(MarketStatsFilters(region="PT-08", city="Faro"))
    assert result["schema_version"] == "1.0"
    assert result["currency"] == "EUR"
    assert result["coverage"]["market"] == "PT"
    assert result["coverage"]["region"] == "PT-08"
    data = result["data"]
    assert data is not None
    assert data["inventory_active"] >= 1
    assert data["median_price_per_m2"] is not None
    assert data["sample_size"] >= 1
    assert "stale_rate" in data
    assert "median_days_on_market" in data


@pytest.mark.asyncio
async def test_unsupported_market_structured_200(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/market/stats",
        json={"region": "GR-I", "city": "Athens"},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"] is None
    assert "unsupported_market" in body["limitations"]


@pytest.mark.asyncio
async def test_market_stats_rest_metered(client: AsyncClient, db_session: AsyncSession) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    resp = await client.post(
        "/v1/market/stats",
        json={"region": "PT-08", "typology": "T2"},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["median_price_eur"] is not None
