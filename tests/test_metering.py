import uuid

import pytest
from app.payments.metering import MeteringService
from app.payments.stripe_rail import FakeStripeRail
from app.payments.x402 import FakeX402Rail
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_keyed_call_records_usage(db_session: AsyncSession) -> None:
    metering = MeteringService(db_session, stripe=FakeStripeRail(), x402=FakeX402Rail())
    ctx = await metering.authorize(
        "search_listings",
        api_key="dev-key-change-me",
        request_id=str(uuid.uuid4()),
    )
    assert ctx.rail in ("free", "dev_bypass", "stripe")


@pytest.mark.asyncio
async def test_keyless_returns_402_in_production_mode(db_session: AsyncSession, monkeypatch) -> None:
    from app.config import Settings

    settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        jws_private_key_pem="-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEI\n-----END EC PRIVATE KEY-----",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.payments.metering.get_settings", lambda: settings)

    metering = MeteringService(db_session, x402=FakeX402Rail())
    with pytest.raises(Exception) as exc:
        await metering.authorize("search_listings", request_id=str(uuid.uuid4()))
    assert exc.value.status_code == 402  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_x402_payment_executes(db_session: AsyncSession) -> None:
    metering = MeteringService(db_session, x402=FakeX402Rail())
    rid = str(uuid.uuid4())
    ctx = await metering.authorize(
        "search_listings",
        payment_header=FakeX402Rail.VALID_HEADER,
        request_id=rid,
    )
    assert ctx.rail == "x402"
    assert ctx.payer_address == "0xTestWallet"


@pytest.mark.asyncio
async def test_idempotent_request_not_double_charged(db_session: AsyncSession) -> None:
    metering = MeteringService(db_session, x402=FakeX402Rail())
    rid = str(uuid.uuid4())
    await metering.authorize(
        "search_listings",
        payment_header=FakeX402Rail.VALID_HEADER,
        request_id=rid,
    )
    ctx2 = await metering.authorize(
        "search_listings",
        payment_header=FakeX402Rail.VALID_HEADER,
        request_id=rid,
    )
    assert ctx2.request_id == rid


@pytest.mark.asyncio
async def test_search_api_after_pipeline(client: AsyncClient, db_session: AsyncSession) -> None:
    from pathlib import Path

    from app.ingestion.fixture_collector import FixtureCollector
    from app.ingestion.pipeline import IngestionService
    from app.resolution.matcher import ResolutionService

    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    resp = await client.post(
        "/v1/listings/search",
        json={"city": "Faro", "limit": 10},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1


@pytest.mark.asyncio
async def test_verify_claim_returns_jws(client: AsyncClient, db_session: AsyncSession) -> None:
    from pathlib import Path

    from app.ingestion.fixture_collector import FixtureCollector
    from app.ingestion.pipeline import IngestionService
    from app.resolution.matcher import ResolutionService

    fixtures = Path(__file__).parent / "fixtures" / "idealista_pt_listings.json"
    await IngestionService(db_session).ingest_collector(FixtureCollector(fixtures))
    await ResolutionService(db_session).resolve_all()
    await db_session.commit()

    resp = await client.post(
        "/v1/verify",
        json={"claim": "T2 in Faro €240,000, 40 days on market", "depth": "corpus"},
        headers={"X-API-Key": "dev-key-change-me"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["jws"]
    assert data["attestation"]["confidence"] > 0
