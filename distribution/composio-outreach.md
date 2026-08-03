# Composio Partner Outreach — Attesta

**Subject:** Attesta MCP — Portugal property data + signed verification for agent workflows

Hi Composio team,

We built **Attesta** — a metered MCP server selling provenance-grade Portugal residential property data and signed JWS claim verification to AI agents.

**MCP endpoint:** `https://api.attesta.dev/mcp` (streamable HTTP)

**Tools (6):**
- `search_listings` — deduplicated PT residential search
- `get_property` / `get_price_history` / `get_market_stats` / `get_comps`
- `check_listing_freshness` — phantom/delisted detection
- `verify_claim` — natural-language claim → verdicts + ES256 JWS attestation

**Why Composio users care:** Proptech agents, golden-visa relocation bots, and EU compliance workflows need grounded property facts with audit trails (EU AI Act Article 50 positioning).

**Integration ask:** List Attesta as a discoverable MCP destination in Composio's toolkit catalog, or feature us in a proptech agent template. We can provide a design-partner API key with 10k free calls/month.

**Demo claim:** `verify_claim(claim="T2 in Faro €240k, 40 days on market", depth="corpus")`

Happy to do a 15-min integration call.

— Dor, Attesta
