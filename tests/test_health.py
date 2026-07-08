import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_jwks_endpoint(client: AsyncClient) -> None:
    resp = await client.get("/.well-known/jwks.json")
    assert resp.status_code == 200
    data = resp.json()
    assert "keys" in data
    assert data["keys"][0]["alg"] == "ES256"


@pytest.mark.asyncio
async def test_mcp_server_card(client: AsyncClient) -> None:
    resp = await client.get("/.well-known/mcp/server-card.json")
    assert resp.status_code == 200
    data = resp.json()
    assert data["serverInfo"]["name"] == "Attesta"
    assert len(data["tools"]) == 6


@pytest.mark.asyncio
async def test_llms_txt(client: AsyncClient) -> None:
    resp = await client.get("/llms.txt")
    assert resp.status_code == 200
    assert "Attesta" in resp.text
    assert "verify_claim" in resp.text
