# Attesta Launch Runbook

One-page checklist to go from repo → live product people can try.

## What you have (MVP complete)

| Layer | Status |
|-------|--------|
| 6 MCP tools + REST mirror | ✅ |
| Fixture corpus (~40 PT listings) | ✅ |
| Entity resolution + staleness | ✅ |
| JWS attestations + JWKS | ✅ |
| Metering (Stripe + x402 scaffolds) | ✅ |
| Eval harness (62 claims, 75% threshold) | ✅ |
| 26 tests passing | ✅ |

## Business model (from DISTRIBUTION.md)

**Positioning:** Provenance-grade EU property data + signed verification receipts for AI agents — per call, no account, USDC or Stripe.

**Phase 0 goal:** Live endpoint + 3 directory listings + first external usage.

**Revenue rails:** Stripe today (human operators), x402 as agent-economy option.

**Killer demo:** Agent calls `verify_claim("T2 in Faro €240k, 40 days on market")` → gets JWS attestation.

---

## Step 1 — Deploy (Railway + Neon)

Infrastructure already provisioned:

- **Railway project:** `attesta` (`368ba9cd-3c35-4ced-840d-ca19ed9b97be`)
- **Neon project:** `attesta` (`super-water-47838213`)

```bash
# Generate secrets (saves .env.production — gitignored)
python scripts/generate_production_env.py \
  --database-url "postgresql+asyncpg://USER:PASS@HOST/neondb?ssl=require" \
  --public-base-url "https://YOUR-RAILWAY-URL.up.railway.app"

# Migrate + seed locally (or via railway run)
set -a && source .env.production && set +a
alembic upgrade head
attesta-ingest --fixture
attesta-resolve

# Deploy API
railway link -p attesta
railway up --service api

# Smoke test
python scripts/demo.py --base-url https://YOUR-URL --api-key YOUR_DEMO_KEY
```

Save the **demo API key** printed by `generate_production_env.py` — share it with early users.

---

## Step 2 — Directory listings

After deploy, run:

```bash
ATTESTA_BASE_URL=https://YOUR-URL ./scripts/distribute.sh
```

### Anthropic / MCP Official Registry

1. Fix GitHub auth: `gh auth refresh`
2. Update `distribution/server.json` → set `remotes[0].url` to your live `/mcp` URL
3. Install publisher: `go install github.com/modelcontextprotocol/registry/cmd/mcp-publisher@latest`
4. `cd distribution && mcp-publisher login github && mcp-publisher publish`

Namespace: `io.github.doralboim/attesta`

### Smithery

1. Go to [smithery.ai/new](https://smithery.ai/new)
2. Enter `https://YOUR-URL/mcp`
3. Config schema: `distribution/smithery-config.json`
4. Or CLI: `npx @smithery/cli mcp publish "https://YOUR-URL/mcp" -n @doralboim/attesta`

Server card at `/.well-known/mcp/server-card.json` helps Smithery scan without auth walls.

### Composio

No public self-serve listing for third-party MCP servers yet. Use `distribution/composio-outreach.md` template → email partners@composio.dev. Ask for toolkit catalog listing or proptech agent template featuring Attesta.

### Claude Desktop / Cursor (for demos)

Copy `distribution/claude-desktop.json` or `distribution/cursor-mcp.json`, replace API key.

---

## Step 3 — Let people play

| Audience | Entry point |
|----------|-------------|
| Agent devs | `/mcp` + `/llms.txt` + OpenAPI at `/docs` |
| Humans | `/docs` Swagger UI — try REST with demo API key |
| Skeptics | `scripts/demo.py` + JWS validate endpoint |
| Investors | Faro demo + attestation spec at `public/attestation-spec.md` |

**Free tier:** 200 calls/month per API key (bootstrap key for demo).

---

## Step 4 — Enable payments (week 2)

1. **Stripe:** Create metered product, set `STRIPE_SECRET_KEY`, issue API keys
2. **x402:** Set `X402_ENABLED=true`, `X402_EVM_ADDRESS`, test on Base Sepolia then mainnet
3. Post demo in x402 Discord + MCP Discord

---

## Blockers requiring your decision

| Item | Options |
|------|---------|
| GitHub repo | No commits yet — push to `doralboim/attesta` for MCP registry namespace |
| Custom domain | `api.attesta.dev` vs Railway default URL |
| Live ingestion | Keep fixtures for demo, or wire Apify for production corpus |
| LLM verification | `LLM_ENABLED=true` + `ANTHROPIC_API_KEY` for live verify_claim adjudication |
| Legal entity | EU jurisdiction for GDPR/AI Act positioning |

---

## Value proposition (what users should feel in 30 seconds)

1. **Search** Faro listings — deduplicated across portals
2. **Check freshness** — staleness score before recommending a property
3. **Verify a claim** — "€240k, 40 days on market" → CORROBORATED/CONTRADICTED + signed JWS
4. **Offline verify** — anyone validates JWS against `/.well-known/jwks.json`

That is the moat: provenance substrate + machine-readable audit receipts, sold per call to agents.
