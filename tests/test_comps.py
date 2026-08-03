"""Comps filtering and envelope contract."""

import uuid
from pathlib import Path

import pytest
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.serving.aggregates import area_within_tolerance
from app.serving.tools import CompsFilters, SearchFilters, ToolService
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def test_area_within_tolerance() -> None:
    assert area_within_tolerance(80, 80, 15) is True
    assert area_within_tolerance(90, 80, 15) is True  # 12.5%
    assert area_within_tolerance(100, 80, 15) is False
    assert area_within_tolerance(68, 80, 15) is True


@pytest.mark.asyncio
async def test_get_comps_excludes_self_and_flags_thin_sample(
    db_session: AsyncSession,
) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    # Faro T2 ~78–79 m² resolves to one property (cross-portal match)
    svc = ToolService(db_session)
    search = await svc.search_listings(SearchFilters(region="PT-08", city="Faro", typology="T2", limit=10))
    assert search["count"] >= 1
    self_id = search["listings"][0]["id"]

    result = await svc.get_comps(
        CompsFilters(
            region="PT-08",
            city="Faro",
            typology="T2",
            area_m2=78,
            area_tolerance_pct=15,
            property_id=uuid.UUID(self_id),
            limit=50,
        )
    )
    assert result["schema_version"] == "1.0"
    assert result["data"] is not None
    ids = {c["property_id"] for c in result["data"]["comps"]}
    assert self_id not in ids
    # Thin Faro T2 corpus after excluding self
    assert "sample_size_lt_5" in result["limitations"]


@pytest.mark.asyncio
async def test_comps_rest_endpoint(client: AsyncClient, db_session: AsyncSession) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    resp = await client.post(
        "/v1/comps",
        json={
            "region": "PT-08",
            "city": "Faro",
            "area_m2": 78,
            "area_tolerance_pct": 20,
            "limit": 10,
        },
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "comps" in body["data"]
    assert body["data"]["sample_size"] == len(body["data"]["comps"])
