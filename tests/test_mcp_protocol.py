import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_mcp_get_is_not_a_stream(client: AsyncClient) -> None:
    resp = await client.get("/mcp")
    # Mounted apps often 307 to /mcp/; GET must not open an SSE stream (200 + text/event-stream).
    assert resp.status_code in {307, 400, 404, 405, 406}
    if resp.status_code == 200:
        assert "text/event-stream" not in resp.headers.get("content-type", "")


@pytest.mark.asyncio
async def test_mcp_post_accepts_protocol_version_header(client: AsyncClient) -> None:
    resp = await client.post(
        "/mcp",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2026-07-28",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2026-07-28",
                "capabilities": {},
                "clientInfo": {"name": "attesta-test", "version": "0"},
            },
        },
    )
    # FastMCP may speak SSE or JSON; either way the pin must not 404/405.
    assert resp.status_code not in {404, 405}
