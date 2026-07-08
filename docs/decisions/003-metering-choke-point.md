# ADR-003: Metering choke point

**Status:** Accepted (2026-07-05)

**Context:** Architecture §4.2 requires single middleware for Stripe, x402, and free tier.

**Decision:** `MeteringService.authorize()` is called at the start of every priced REST route and MCP tool. Returns 402 with payment spec when unauthenticated in production. Test/dev environments allow `dev_bypass`.

**Consequences:** MCP x402 returns structured 402 via tool error path (future); REST uses HTTP 402. Idempotency via `X-Request-Id` header.
