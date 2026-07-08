# ADR-002: FastMCP for MCP transport

**Status:** Accepted (2026-07-05)

**Context:** Agent prompt specifies official `mcp` SDK. FastMCP 3.x wraps MCP with streamable HTTP.

**Decision:** Use `fastmcp>=3` with `http_app(transport="streamable-http", stateless_http=True)` mounted at `/mcp`. Assumption documented: stateless mode for Railway horizontal scale without sticky sessions.

**Consequences:** SSE transport is not used. Tool auth passes `api_key` param until MCP session auth conventions stabilize.
