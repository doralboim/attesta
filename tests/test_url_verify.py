import pytest
from app.ingestion.fixture_collector import FixtureCollector
from app.ingestion.pipeline import IngestionService
from app.ingestion.url_dispatch import UnsupportedListingUrlError, resolve_collector_for_url
from app.resolution.matcher import ResolutionService
from app.verification.pipeline import VerificationPipeline
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def test_dispatch_idealista_falls_back_to_fixture() -> None:
    collector = resolve_collector_for_url("https://www.idealista.pt/imovel/1001")
    assert isinstance(collector, FixtureCollector)


def test_dispatch_unknown_host() -> None:
    with pytest.raises(UnsupportedListingUrlError):
        resolve_collector_for_url("https://example.com/listing/1")


@pytest.mark.asyncio
async def test_verify_url_roundtrip(db_session: AsyncSession) -> None:
    result = await VerificationPipeline(db_session).verify_url(
        "https://idealista.pt/imovel/1001",
        persist=False,
    )
    payload = result["attestation"]
    assert payload["method"] == "attesta/verify@0.2"
    assert payload["sub_claim"] == "https://idealista.pt/imovel/1001"
    assert result["verification_mode"] == "url"
    predicates = {v["predicate"] for v in payload["verdicts"]}
    assert any(p.startswith("price=") for p in predicates)
    assert "availability" in predicates
    assert all(v.get("source_classes") == ["portal"] for v in payload["verdicts"])


@pytest.mark.asyncio
async def test_verify_url_unknown_host_unverifiable(db_session: AsyncSession) -> None:
    result = await VerificationPipeline(db_session).verify_url(
        "https://example.com/x",
        persist=False,
    )
    assert result["attestation"]["verdicts"][0]["verdict"] == "UNVERIFIABLE"


@pytest.mark.asyncio
async def test_verify_url_api(client: AsyncClient) -> None:
    resp = await client.post(
        "/v1/verify",
        json={"url": "https://idealista.pt/imovel/1001"},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["verification_mode"] == "url"
    assert data["jws"]


@pytest.mark.asyncio
async def test_verify_requires_exactly_one_subject(client: AsyncClient) -> None:
    both = await client.post(
        "/v1/verify",
        json={"claim": "T2", "url": "https://idealista.pt/imovel/1001"},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert both.status_code == 422
    neither = await client.post(
        "/v1/verify",
        json={},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert neither.status_code == 422


@pytest.mark.asyncio
async def test_deep_mode_refreshes_from_fixture_url(db_session: AsyncSession) -> None:
    await IngestionService(db_session).ingest_collector(FixtureCollector())
    await ResolutionService(db_session).resolve_all()

    result = await VerificationPipeline(db_session).verify(
        "T2 in Faro €240,000, 40 days on market",
        depth="deep",
        persist=False,
    )
    assert result["verification_mode"] == "deep"
    assert result["attestation"]["confidence"] > 0
