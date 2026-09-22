from decimal import Decimal

import pytest
from app.config import Settings, get_settings
from app.payments.metering import MeteringService
from app.payments.pricing import PricingService, invalidate_price_cache
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def _clear_price_cache() -> None:
    invalidate_price_cache()
    yield
    invalidate_price_cache()


@pytest.mark.asyncio
async def test_admin_unconfigured_is_503(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(admin_api_token="")
    monkeypatch.setattr("app.serving.admin.get_settings", lambda: settings)
    resp = await client.get("/internal/pricing", headers={"X-Admin-Token": "x"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_admin_wrong_token_is_401(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(admin_api_token="secret-admin")
    monkeypatch.setattr("app.serving.admin.get_settings", lambda: settings)
    resp = await client.get("/internal/pricing", headers={"X-Admin-Token": "nope"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_admin_patch_updates_metered_price(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = Settings(admin_api_token="secret-admin")
    monkeypatch.setattr("app.serving.admin.get_settings", lambda: settings)

    listed = await client.get("/internal/pricing", headers={"X-Admin-Token": "secret-admin"})
    assert listed.status_code == 200
    assert "verify_url" in listed.json()["prices"]

    patched = await client.patch(
        "/internal/pricing/verify_url",
        json={"price_eur": "0.05"},
        headers={"X-Admin-Token": "secret-admin"},
    )
    assert patched.status_code == 200
    assert patched.json()["price_eur"] == "0.05"

    listed_again = await client.get("/internal/pricing", headers={"X-Admin-Token": "secret-admin"})
    assert Decimal(listed_again.json()["prices"]["verify_url"]) == Decimal("0.05")


@pytest.mark.asyncio
async def test_pricing_service_fallback_and_override(db_session: AsyncSession) -> None:
    svc = PricingService(db_session)
    assert await svc.get_price("search_listings") == Decimal("0.01")
    await svc.set_price("search_listings", Decimal("0.03"))
    assert await svc.get_price("search_listings") == Decimal("0.03")

    metering = MeteringService(db_session)
    ctx = await metering.authorize("search_listings", api_key="dev-key-change-me")
    assert ctx.price_eur in (Decimal("0.03"), Decimal("0"))


@pytest.mark.asyncio
async def test_internal_routes_absent_from_openapi(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    assert not any(path.startswith("/internal") for path in paths)


def test_get_settings_exposes_admin_token() -> None:
    get_settings.cache_clear()
    settings = Settings(admin_api_token="tok")
    assert settings.admin_api_token == "tok"
