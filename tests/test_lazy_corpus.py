from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.db.models import Property
from app.ingestion.base import RawListing
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.resolution.matcher import ResolutionService
from app.serving.lazy_corpus import bind_requested_place, lazy_corpus, place_slug, portal_search_urls
from httpx import AsyncClient
from sqlalchemy import select


@pytest.fixture(autouse=True)
def _reset_lazy_corpus():
    lazy_corpus.reset()
    yield
    lazy_corpus.reset()


def test_portal_urls_are_scoped_to_the_city() -> None:
    idealista, imovirtual = portal_search_urls("Portimão")
    assert idealista == ["https://www.idealista.pt/comprar-casas/portimao/"]
    assert imovirtual == ["https://www.imovirtual.com/pt/resultados/comprar/apartamento/portimao/portimao"]
    assert place_slug("São Brás") == "sao-bras"


def test_bind_drops_other_cities_and_fills_generic_region() -> None:
    other = RawListing(
        source="idealista_pt",
        source_listing_id="x",
        url="https://example.test/x",
        observed_at=datetime.now(UTC),
        price_eur=1,
        status="active",
        attrs={"city": "Lisboa", "region": "PT"},
    )
    assert bind_requested_place(other, "Lagos", "PT-08") is False

    missing = RawListing(
        source="idealista_pt",
        source_listing_id="y",
        url="https://example.test/y",
        observed_at=datetime.now(UTC),
        price_eur=1,
        status="active",
        attrs={"region": "PT"},
    )
    assert bind_requested_place(missing, "Lagos", "PT-08") is True
    assert missing.attrs["city"] == "Lagos"
    assert missing.attrs["region"] == "PT-08"


def _lagos_listing() -> RawListing:
    return RawListing(
        source="idealista_pt",
        source_listing_id="lagos-1",
        url="https://example.test/lagos-1",
        observed_at=datetime.now(UTC),
        price_eur=310000,
        status="active",
        attrs={"city": "Lagos", "region": "PT", "typology": "T2"},
    )


@pytest.mark.asyncio
async def test_search_reports_updating_then_saves_only_the_requested_city(client: AsyncClient, db_session) -> None:
    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()

    calls = {"n": 0}

    async def fake_fetch(filters):
        calls["n"] += 1
        assert filters.city == "Lagos"
        return [_lagos_listing()]

    lazy_corpus.fetcher = fake_fetch

    started = await client.post("/v1/listings/search", json={"city": "Lagos", "region": "PT-08"})
    assert started.status_code == 200
    body = started.json()
    assert body["coverage"]["status"] == "updating"
    assert "Lagos" in body["coverage"]["message"]
    job_id = body["coverage"]["job_id"]

    events = await client.get(f"/v1/listings/ingest/{job_id}/events")
    assert events.status_code == 200
    assert "text/event-stream" in events.headers["content-type"]
    assert '"status": "ready"' in events.text
    assert "Saved 1 observations for Lagos." in events.text

    again = await client.post("/v1/listings/search", json={"city": "Lagos", "region": "PT-08"})
    saved = again.json()
    assert saved["coverage"]["status"] == "ready"
    assert saved["count"] == 1
    assert saved["listings"][0]["city"] == "Lagos"
    assert calls["n"] == 1

    props = (await db_session.execute(select(Property))).scalars().all()
    faro = [p for p in props if p.canonical_attrs.get("city") == "Faro"]
    assert any(p.is_active for p in faro)


@pytest.mark.asyncio
async def test_search_without_a_city_does_not_fetch(client: AsyncClient) -> None:
    async def fake_fetch(_filters):
        raise AssertionError("fetch should not run")

    lazy_corpus.fetcher = fake_fetch
    resp = await client.post("/v1/listings/search", json={"region": "PT-08"})
    assert resp.status_code == 200
    assert resp.json()["coverage"]["status"] == "needs_city"
