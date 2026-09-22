# ADR-011: Dynamic pricing via internal ops API

**Status:** Accepted (2026-09-21)

**Context:** Tool prices lived in a hardcoded dict. We need to change prices without a redeploy, including a new `verify_url` SKU, without building an admin dashboard (explicit non-goal in `docs/MISSION.md`).

**Decision:** Persist overrides in `tool_prices`. `PricingService.get_price` reads DB with a 30s in-process cache, falling back to `DEFAULT_TOOL_PRICES_EUR`. Operators update prices via `GET/PATCH /internal/pricing`, authenticated with `X-Admin-Token` against `ADMIN_API_TOKEN`. The router is `include_in_schema=False` and is not listed in `llms.txt` or the MCP server card.

The admin endpoints bypass `MeteringService` — they are operator actions, not priced customer calls. If `ADMIN_API_TOKEN` is unset the endpoints return 503.

**Consequences:** A leaked customer API key cannot reprice the system. Cache invalidation on write keeps `authorize()` cheap. Seed `verify_url` at €0.08 (same cost driver as deep: one live fetch).
