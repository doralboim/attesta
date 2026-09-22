"""Tests for free-tier API key minting and exhaustion."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.config import Settings
from app.db.models import ApiKey, UsageEvent
from app.ingestion.pii_strip import hash_api_key
from app.payments.metering import MeteringService
from app.payments.stripe_rail import FakeStripeRail
from app.payments.x402 import FakeX402Rail
from app.serving.rest import MINT_RATE_LIMIT_PER_HOUR
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_mint_api_key_returns_raw_once(client: AsyncClient, db_session: AsyncSession) -> None:
    resp = await client.post("/v1/keys")
    assert resp.status_code == 200
    body = resp.json()
    assert "api_key" in body
    assert body["monthly_free_calls"] == 200
    raw = body["api_key"]
    stored = await db_session.get(ApiKey, hash_api_key(raw))
    assert stored is not None
    assert stored.plan == "metered"
    assert stored.is_active is True
    assert stored.key_hash == hash_api_key(raw)
    assert stored.key_hash != raw


@pytest.mark.asyncio
async def test_mint_rate_limit_returns_429(client: AsyncClient, db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    for i in range(MINT_RATE_LIMIT_PER_HOUR):
        db_session.add(
            ApiKey(
                key_hash=f"seed-{i}",
                plan="metered",
                monthly_free_calls=200,
                is_active=True,
                created_at=now - timedelta(minutes=5),
            )
        )
    await db_session.commit()

    resp = await client.post("/v1/keys")
    assert resp.status_code == 429
    assert resp.json()["detail"]["code"] == "mint_rate_limit_exceeded"


@pytest.mark.asyncio
async def test_free_tier_exhausted_without_stripe_returns_402(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = Settings(
        environment="production",
        database_url="sqlite+aiosqlite:///:memory:",
        stripe_secret_key="",
        free_tier_monthly_calls=2,
        jws_private_key_pem="-----BEGIN EC PRIVATE KEY-----\nMHcCAQEEI\n-----END EC PRIVATE KEY-----",
    )
    monkeypatch.setattr("app.config.get_settings", lambda: settings)
    monkeypatch.setattr("app.payments.metering.get_settings", lambda: settings)

    raw = "caller-key-for-exhaustion-test"
    key_hash = hash_api_key(raw)
    db_session.add(ApiKey(key_hash=key_hash, plan="metered", monthly_free_calls=2, is_active=True))
    for _ in range(2):
        db_session.add(
            UsageEvent(
                rail="free",
                key_hash=key_hash,
                tool="search_listings",
                price_eur=0,
                request_id=str(uuid.uuid4()),
            )
        )
    await db_session.commit()

    metering = MeteringService(db_session, stripe=FakeStripeRail(), x402=FakeX402Rail())
    with pytest.raises(Exception) as exc:
        await metering.authorize("search_listings", api_key=raw, request_id=str(uuid.uuid4()))
    assert exc.value.status_code == 402  # type: ignore[attr-defined]
    assert exc.value.detail == {"code": "free_tier_exhausted"}  # type: ignore[attr-defined]
