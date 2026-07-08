# Attesta — Distribution Playbook

This guide maps directly to the company design doc's Phase 0–2 GTM sequence.

## Positioning (one sentence for every channel)

> Attesta sells provenance-grade EU property data and signed verification receipts to AI agents — per call, no account, payable in USDC or Stripe.

Lead with **measured** numbers when pitching humans; lead with **tool descriptions** when listing in agent directories.

---

## Phase 0 — Weeks 1–4: Ship the seller

**Goal:** Live MCP + REST endpoint, listed in 3+ directories, first external agent usage generating revenue.

### Week 1 checklist
- [x] FastAPI + MCP server with 6 tools
- [x] Stripe metering scaffold
- [x] x402 middleware scaffold
- [x] JWS attestation on verify_claim
- [x] MCP discovery assets (`/.well-known/mcp/server-card.json`, `distribution/server.json`)
- [x] Client config snippets (Claude Desktop, Cursor, Smithery)
- [x] Distribution script (`scripts/distribute.sh`)
- [ ] Seed production Postgres via fixture ingest (or chosen live collector)
- [ ] Deploy to Railway with public URL
- [ ] Dogfood: internal agent workflows calling Attesta MCP/REST

### Week 2 checklist
- [ ] Enable x402 on Base Sepolia → mainnet
- [x] Publish `llms.txt` at root URL (dynamic `PUBLIC_BASE_URL`)
- [ ] Submit to directories (below)

### Week 3 checklist
- [ ] Publish "How wrong is portal data?" benchmark blog post
- [ ] verify_claim GA with live-fetch for Idealista/Imovirtual
- [ ] First external paying operator

---

## Tier 1 — Distribution directories (highest leverage, weeks 1–6)

Submit in this order. Tool descriptions matter more than marketing copy — write for **model tool-selection**.

| Channel | URL | What to submit | Why |
|---------|-----|----------------|-----|
| Anthropic MCP Registry | https://github.com/modelcontextprotocol/servers | MCP manifest + public endpoint | Default discovery for Claude |
| Smithery | https://smithery.ai | Hosted MCP listing | High-traffic MCP search |
| PulseMCP | https://www.pulsemcp.com | Server listing | Agent builder audience |
| mcpmarket.com | https://mcpmarket.com | Server listing | Long-tail discovery |
| mcpservers.org | https://mcpservers.org | Server listing | SEO compounding |
| Coinbase Agentic.market / x402 Bazaar | CDP developer portal | x402 seller listing | Account-less agent buyers |
| Pay.sh catalog | Solana/Google Cloud repo | Provider PR | Gemini/Codex agents with wallets |
| Apify Store | https://apify.com/store | Attesta Actor (pay-per-event) | Optional distribution channel if you publish a scraper actor |

**Submission assets you already have:**
- MCP endpoint: `https://your-domain/mcp`
- OpenAPI: `https://your-domain/docs`
- `llms.txt`: machine-readable product summary
- Demo claim: Faro T2 at €240k, 40 days — verify_claim returns JWS

**Ecosystem hack:** x402 and MCP protocol teams actively amplify real sellers. Post a working demo in their Discord with a screen recording of an agent paying per call.

---

## Tier 2 — Integration partners (months 2–4)

Build the integration yourself first (1 day each), then pitch DevRel with usage numbers.

| Partner | Integration | Pitch angle |
|---------|-------------|-------------|
| LangChain / LangGraph | `AttestaVerify` tool wrapper | "Ground truth for property agents" |
| CrewAI | Custom tool | EU proptech agent templates |
| n8n / Make | HTTP node recipes | No-code agent builders |
| ATXP / Coinbase Agentic Wallets | Featured spend destination | Flagship x402 merchant |
| EU proptech startups | Design partner access | 5-min MCP demo = the pitch |

**Outreach template (founder-to-founder):**

> We built per-call verified property data for Portugal/Greece over MCP + x402. Your agent can call `search_listings` and `verify_claim` in 30 seconds — no contract. Want a free 10k calls/month design-partner key?

Target 30 proptech/agent startups: Idealista partner ecosystem, YC proptech batch, golden-visa relocation services.

---

## Tier 3 — Content as distribution (GEO flywheel)

Agents cite authoritative benchmarks. Publish:

1. **"How wrong is portal data?"** — duplicate rate, phantom listings, price delta across portals (Bank of Italy cites ~2 month time-on-market overestimate from raw listings)
2. **Attestation spec v1** — open JSON schema for JWS receipts; other services verify your signatures
3. **Verification precision eval** — hand-labeled set, publish precision/recall

Post to: Hacker News (Show HN), r/LocalLLaMA, x402 Discord, MCP Discord, LinkedIn (EU proptech angle).

---

## Pricing & rails strategy

| Product | Price | Primary rail |
|---------|-------|--------------|
| Data query | €0.005–0.02 | Both |
| Data heavy | €0.05–0.10 | Both |
| Verify corpus | €0.02 | x402-first |
| Verify deep | €0.05–0.10 | Both |
| Enterprise snapshot | €500–2,000/mo | Stripe contract |

**Leading indicator:** Track `x402_revenue : stripe_revenue` ratio monthly. Rising x402 share = agent economy arriving on your rails.

**Honest investor framing:** Revenue runs on Stripe today; x402 is a near-free call option.

---

## Phase 1 targets (weeks 5–12)

- 10 paying agent operators
- €500 MRR
- Listed in all Tier 1 directories
- Greece corpus live
- 1 benchmark post with measurable portal-error data

## Phase 2 targets (months 4–9)

- verify_claim GA + attestation spec published
- 1 portal licensing deal (Idealista or Imovirtual)
- €5k MRR
- 1 lighthouse logo (proptech platform or fund)

---

## Regulatory positioning (EU AI Act)

Article 50 transparency obligations apply **August 2, 2026**. Position Attesta Verify as:

> Audit-trail-as-a-service for EU agent deployments — a machine-readable attestation receipt operators can file.

This is a **sales feature**, not just compliance theater.

---

## KPIs to run weekly

| Metric | Target | Why |
|--------|--------|-----|
| Calls/month | Growing 20%+ MoM | Core usage |
| Paying wallets + API keys | Split by rail | Buyer mix |
| x402:Stripe revenue ratio | Trending up | Agent economy signal |
| Corpus freshness lag | <6 hours | Data quality |
| Verification precision | Publish quarterly | Trust product |
| Directory-sourced traffic | >30% of new keys | Discovery working |
| Gross margin per call | >85% | Unit economics |

---

## What NOT to do early

- Don't lead with TAM slides to developers — lead with a 30-second MCP demo
- Don't wait for enterprise portal licenses before shipping — scrape compliant, license later
- Don't bet the business on x402 volume today (~$3M/mo agent-specific per Allium Labs) — Stripe keeps you alive
- Don't put unverified stats on marketing (AgentHallu exact figures, Gartner $12.8B hallucination market)

---

## Immediate next actions for you

1. **Deploy to Railway** — project `attesta` created (ID `368ba9cd-3c35-4ced-840d-ca19ed9b97be`). Neon Postgres `attesta` project ready (ID `super-water-47838213`). Run:
   ```bash
   python scripts/generate_production_env.py \
     --database-url "postgresql+asyncpg://USER:PASS@HOST/neondb?ssl=require" \
     --public-base-url "https://YOUR-RAILWAY-URL"
   railway link -p attesta
   railway up --service api
   railway run --service ingest-worker attesta-ingest --fixture
   railway run --service resolve-worker attesta-resolve
   ATTESTA_BASE_URL=https://YOUR-URL ./scripts/distribute.sh
   ```
2. **Choose a live ingestion path** — fixtures work for dev/demo; production needs a collector (Apify actors, direct scraper, licensed feed, or CSV import). See `docs/decisions/008-fixture-first-ingestion.md`.
3. **Confirm entity jurisdiction** — EU base for GDPR/AI Act story
4. **Set x402 wallet address** — enable USDC rail on deploy
5. **Create Stripe meter + product** — for human/agent-operator billing
6. **Publish to directories** — run `./scripts/distribute.sh` after deploy; follow MCP Registry + Smithery steps inside
7. **Record 60-second demo** — Claude agent evaluates Faro apartment via Attesta, pays via x402
