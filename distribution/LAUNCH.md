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

## Step 1 — Deploy (Railway + Neon) ✅ DONE

**Live URL (Railway):** https://api-production-d9143.up.railway.app  
**Custom domain (pending DNS):** https://api.attesta.dev

Neon DB migrated and seeded (5 properties, Faro corpus). Demo API key is in your local `.env.production` (also set on Railway as `BOOTSTRAP_API_KEY`).

**Production ingest-worker start command:** `attesta-ingest --live` (requires `APIFY_TOKEN`). Do not leave it on `--fixture`.

### DNS for api.attesta.dev (add at your domain registrar)

| Type | Name | Value |
|------|------|-------|
| CNAME | `api` | `e7qlv9c0.up.railway.app` |
| TXT | `_railway-verify.api` | `railway-verify=c2dfa302195aae27ed5be6d9676ce202bc2a535a7a0ca89a068366088083c224` |

`attesta.dev` is not in your Cloudflare account — add these records wherever you manage DNS.

### Verify locally

```bash
python scripts/demo.py --base-url https://api-production-d9143.up.railway.app --api-key $(grep BOOTSTRAP_API_KEY .env.production | cut -d= -f2)
```

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
| Live ingestion | Production Railway ingest-worker start command must be `attesta-ingest --live` (not `--fixture`) |
| LLM verification | `LLM_ENABLED=true` + `ANTHROPIC_API_KEY` for live verify_claim adjudication |
| Legal entity | EU jurisdiction for GDPR/AI Act positioning |

---

## Value proposition (what users should feel in 30 seconds)

1. **Search** Faro listings — deduplicated across portals
2. **Check freshness** — staleness score before recommending a property
3. **Verify a claim** — "€240k, 40 days on market" → CORROBORATED/CONTRADICTED + signed JWS
4. **Offline verify** — anyone validates JWS against `/.well-known/jwks.json`

That is the moat: provenance substrate + machine-readable audit receipts, sold per call to agents.
