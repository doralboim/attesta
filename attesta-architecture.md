# Attesta — Technical Architecture Design (MVP → v1)

Target: first invoice-able call in ~3 weeks, solo-maintained, deployed on Railway. Everything below is scoped to be buildable by one senior engineer with Claude Code.

---

## 1. System overview

```
                        ┌──────────────────────────────────────────────┐
                        │                ATTESTA PLATFORM              │
                        │                                              │
  Idealista ──┐         │  ┌───────────┐   ┌────────────┐             │
  Imovirtual ─┼─collectors▶│  │ INGESTION │──▶│ RESOLUTION │──┐          │
  Casa Sapo ──┘ (pluggable)│  │  workers  │   │   worker   │  │          │
                        │  └─────┬─────┘   └────────────┘  ▼          │
                        │        │ raw snapshots      ┌─────────┐     │
                        │        ▼                    │Postgres │     │
                        │  ┌───────────┐              │+pgvector│     │
                        │  │ SNAPSHOT  │              └────┬────┘     │
                        │  │  STORE    │◀──────────────────┤          │
                        │  │ (S3/R2)   │   evidence reads  │          │
                        │  └───────────┘                   ▼          │
                        │                          ┌──────────────┐   │
   MCP clients ────────▶│  ┌────────────────┐      │ VERIFICATION │   │
   (Claude, Cursor,     │  │  SERVING LAYER │─────▶│    ENGINE    │   │
    agent frameworks)   │  │ FastAPI:       │      │ (Anthropic   │   │
                        │  │  /mcp (strea-  │      │  API, Haiku) │   │
   REST clients ───────▶│  │   mable HTTP)  │      └──────┬───────┘   │
                        │  │  /v1/* (REST)  │             ▼           │
   x402 agents ────────▶│  │  metering MW   │      ┌──────────────┐   │
                        │  └────────────────┘      │ ATTESTATION  │   │
                        │        │                 │ SIGNER (JWS) │   │
                        │        ▼                 └──────────────┘   │
                        │  Stripe (metered) · Coinbase x402 facilitator│
                        └──────────────────────────────────────────────┘
```

One deployable FastAPI app + two background worker processes (ingestion, resolution) sharing a Postgres database. Monorepo, single Docker image, Railway services differ only by start command.

---

## 2. Stack decisions (and why)

| Concern | Choice | Rationale |
|---|---|---|
| Language/framework | Python 3.12, FastAPI, Pydantic v2 | Your daily stack; MCP SDK + Stripe + async all first-class |
| MCP transport | `mcp` Python SDK, streamable HTTP mounted at `/mcp` | Remote-hostable (stdio is local-only); one process serves MCP + REST |
| DB | Postgres 16 + pgvector (Railway addon) | Concurrent metered reads kill SQLite; pgvector for entity-resolution embeddings |
| Raw snapshot store | Cloudflare R2 (S3 API) | Cheap, zero egress fees; snapshots are the provenance substrate — never delete |
| Scrapers | Pluggable `BaseCollector` subclasses; fixtures default; Apify optional | Pipeline testable without external deps; swap in live source when ready |
| Queue/scheduling | Postgres-backed jobs (`procrastinate` or plain cron tables) | No Redis/Celery ops burden at this scale |
| LLM | Anthropic API — Haiku for adjudication, Sonnet for claim parsing fallback | COGS: fractions of a cent per verification |
| Payments (fiat) | Stripe metered billing (usage records per call) | Standard; API keys map to Stripe subscription items |
| Payments (agent) | x402 middleware + Coinbase CDP facilitator, USDC on Base | Never custody funds; facilitator settles |
| Signing | ES256 JWS via `joserkit`/`python-jose`; keypair in env, public key at `/.well-known/jwks.json` | Standard verifiable receipts |
| Deploy | Railway (API + workers + Postgres), R2 external | Your preferred platform |
| Observability | structlog JSON + Railway logs; `/metrics` Prometheus optional later | Keep thin |

---

## 3. Data model (Postgres)

```sql
-- Provenance substrate: immutable, append-only
CREATE TABLE snapshots (
  id            BIGSERIAL PRIMARY KEY,
  source        TEXT NOT NULL,              -- 'idealista_pt', 'imovirtual', ...
  url           TEXT NOT NULL,
  fetched_at    TIMESTAMPTZ NOT NULL,
  content_hash  TEXT NOT NULL,              -- sha256 of raw payload
  storage_key   TEXT NOT NULL,              -- R2 object key
  http_status   INT,
  UNIQUE (source, url, content_hash)
);

-- Source-level listing observations (one row per source per listing per change)
CREATE TABLE observations (
  id            BIGSERIAL PRIMARY KEY,
  snapshot_id   BIGINT REFERENCES snapshots(id),
  source        TEXT NOT NULL,
  source_listing_id TEXT NOT NULL,
  observed_at   TIMESTAMPTZ NOT NULL,
  price_eur     NUMERIC,
  status        TEXT,                       -- 'active' | 'delisted' | 'reserved'
  attrs         JSONB NOT NULL,             -- typology, area_m2, location, features
  geo           POINT,
  embedding     VECTOR(384)                 -- for cross-portal matching
);
CREATE INDEX ON observations (source, source_listing_id, observed_at DESC);

-- Canonical entities after cross-portal resolution
CREATE TABLE properties (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_attrs JSONB NOT NULL,
  region        TEXT NOT NULL,              -- 'PT-08' (Faro) etc.
  first_seen    TIMESTAMPTZ NOT NULL,
  last_seen     TIMESTAMPTZ NOT NULL,
  is_active     BOOLEAN NOT NULL,
  staleness_score REAL,                     -- phantom-listing probability 0..1
  current_price_eur NUMERIC,
  days_on_market INT
);

CREATE TABLE property_observations (        -- link table; a property has N observations
  property_id   UUID REFERENCES properties(id),
  observation_id BIGINT REFERENCES observations(id),
  match_confidence REAL NOT NULL,
  PRIMARY KEY (property_id, observation_id)
);

CREATE TABLE price_events (                 -- derived, queryable history
  property_id   UUID REFERENCES properties(id),
  event_at      TIMESTAMPTZ NOT NULL,
  kind          TEXT NOT NULL,              -- 'listed'|'price_change'|'delisted'|'relisted'
  price_eur     NUMERIC,
  source        TEXT NOT NULL,
  snapshot_id   BIGINT REFERENCES snapshots(id)
);

-- Billing
CREATE TABLE api_keys (
  key_hash      TEXT PRIMARY KEY,           -- sha256; never store raw
  stripe_customer_id TEXT,
  stripe_subscription_item_id TEXT,
  plan          TEXT NOT NULL DEFAULT 'metered',
  monthly_free_calls INT NOT NULL DEFAULT 200,
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE usage_events (
  id            BIGSERIAL PRIMARY KEY,
  occurred_at   TIMESTAMPTZ DEFAULT now(),
  rail          TEXT NOT NULL,              -- 'stripe' | 'x402' | 'free'
  key_hash      TEXT,                       -- null for x402
  payer_address TEXT,                       -- null for stripe
  tool          TEXT NOT NULL,
  price_eur     NUMERIC NOT NULL,
  request_id    TEXT NOT NULL,
  x402_receipt  JSONB
);

-- Attestations issued
CREATE TABLE attestations (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  issued_at     TIMESTAMPTZ NOT NULL,
  claim         TEXT NOT NULL,
  verdicts      JSONB NOT NULL,
  confidence    REAL NOT NULL,
  evidence_hashes TEXT[] NOT NULL,
  jws           TEXT NOT NULL,
  usage_event_id BIGINT REFERENCES usage_events(id)
);
```

Design invariants: **snapshots are append-only** (provenance breaks if you mutate); every derived fact must be traceable to ≥1 `snapshot_id`; personal data (agent names, phone numbers) is stripped in the ingestion worker *before* anything is written — GDPR at the door, not as a cleanup job.

---

## 4. Serving layer

### 4.1 MCP tools (the storefront — descriptions matter as much as code)

| Tool | Params | Price tier |
|---|---|---|
| `search_listings` | region, filters (price range, typology, area), sort, limit≤50 | query (€0.01) |
| `get_property` | property_id → canonical record + sources + staleness + components | query (€0.01) |
| `get_price_history` | property_id → price_events timeline | query (€0.02) |
| `get_market_stats` | region/city/typology/area band → median € & €/m², inventory, velocity (envelope 1.0) | query (€0.02) |
| `get_comps` | region, area_m2 ±tolerance → comparable actives + median €/m² (envelope 1.0) | query (€0.02) |
| `check_listing_freshness` | property_id → active?, last corroboration, staleness score + components | query (€0.02) |
| `verify_claim` | claim (text), depth ('corpus'\|'deep') → verdicts + attestation | €0.02 / €0.05–0.10 |

Market observation responses use the versioned envelope in `public/market-data-contract.md`. Staleness formula: `docs/decisions/009-staleness-v1.md`.

Tool descriptions must state capability, coverage ("residential listings, Portugal, updated <6h"), cost per call, and one example invocation — written for model tool-selection. Same functions exposed as REST under `/v1/*` with an OpenAPI spec; publish `/llms.txt` describing the service for agent discovery.

### 4.2 Metering middleware (single choke point)

Request flow for every priced endpoint/tool call:

1. **API key present** (header `X-API-Key`) → hash, look up, check active + free-tier remainder → execute → write `usage_events` → push Stripe usage record (async, batched every 60s; never block the response on Stripe).
2. **No key** → respond `402 Payment Required` with x402 payment spec JSON: `{ scheme: "exact", network: "base", asset: USDC, amount, payTo, resource, validUntil }`.
3. **Retry with `X-PAYMENT` header** → verify via Coinbase facilitator (`/verify` then `/settle`) → execute → record usage with `payer_address` + receipt.
4. Guardrails: per-key and per-wallet rate limits (token bucket in Postgres), daily spend caps, idempotency on `request_id` so a retrying agent isn't double-charged. **Caps protect the customer** — runaway agent loops are the #1 trust killer.

MCP complication: MCP tool calls arrive inside the streamable-HTTP session, not as individually priced HTTP requests. Solution: enforce metering *inside* the tool dispatcher (same middleware function), and for x402-over-MCP return a structured tool error carrying the payment spec (per emerging x402+MCP conventions) so the agent can pay and re-invoke. Stripe-keyed MCP sessions authenticate once at connect.

### 4.3 Verification engine (`verify_claim` pipeline)

```
claim text
  │  1. PARSE (Haiku, JSON schema output)
  ▼     → predicates: [{field:'price', op:'=', value:240000, entity_ref:...}, ...]
  │  2. RESOLVE entity → property_id (search corpus; ambiguity → 'unverifiable: entity')
  ▼
  │  3. RETRIEVE evidence per predicate:
  │       corpus: latest observations, price_events, staleness
  │       deep mode only: live re-fetch of source URLs → new snapshots
  ▼
  │  4. ADJUDICATE (Haiku, constrained): per-predicate verdict
  │       CORROBORATED | CONTRADICTED | UNVERIFIABLE, each citing snapshot_ids
  ▼
  │  5. SCORE confidence = f(source count, recency, agreement); deterministic, documented
  ▼
  │  6. SIGN → JWS attestation, persist, return
```

Rules: the adjudicator sees **only retrieved evidence**, never open-ended knowledge; every verdict must cite ≥1 snapshot hash or be UNVERIFIABLE; deep mode's live fetches create new snapshots (verification *feeds* the corpus — the flywheel in code).

### 4.4 Attestation format (v0.1 — publish this spec)

JWS (ES256, compact serialization). Payload:

```json
{
  "iss": "https://api.attesta.dev",
  "iat": 1751724128,
  "jti": "att_9f2c44ab",
  "sub_claim": "T2 apartment, Faro: listed €240,000, 40 days on market",
  "verdicts": [
    {"predicate": "price=240000EUR", "verdict": "CORROBORATED",
     "evidence": ["sha256:9f2c…", "sha256:44ab…"], "sources": 2},
    {"predicate": "days_on_market=40", "verdict": "CORROBORATED",
     "evidence": ["sha256:11d0…"], "sources": 1}
  ],
  "confidence": 0.93,
  "method": "attesta/verify@0.1",
  "coverage": "residential_pt"
}
```

Public key served at `/.well-known/jwks.json`. Anyone can verify offline. Evidence hashes resolve (paid) via `/v1/evidence/{hash}` to snapshot metadata.

---

## 5. Ingestion & resolution workers

**Ingestion** (every 4–6h per source): run configured collector (default: bundled JSON fixtures for dev/CI; production: live subclass) → PII strip → hash → write snapshot to R2 + rows to `snapshots`/`observations` → diff against previous observation per source_listing_id → emit change events. Delisting detection: listing absent from two consecutive runs → status `delisted` (with a re-check fetch before committing, to avoid pagination false positives).

**Resolution** (after each ingestion): block candidate pairs by geohash + typology + area band → score with embedding similarity + attribute agreement → match threshold assigns to existing `property` else creates one → recompute `price_events`, `days_on_market`, `staleness_score` (features: last corroboration age, cross-source disagreement, price vs. region prior). Keep the matcher deterministic and versioned — resolution bugs corrupt the moat.

---

## 6. Security, compliance, ops

API keys hashed at rest; JWS private key + Stripe/CDP secrets in Railway env vars, key rotation supported via `kid` header in JWS. GDPR: PII strip at ingestion (regex + NER pass), no personal data in corpus, R2 EU jurisdiction bucket. Never custody crypto — facilitator settles direct to wallet. Terms: data provided "as observed at sources," attestations attest to *corroboration across sources*, not ground truth of the world (this phrasing matters for liability). Backups: Railway PG daily + R2 is inherently the audit log. Monitoring alarms: ingestion freshness lag > 8h, verification error rate > 2%, Stripe usage-push backlog.

## 7. Build order (maps to the 3-week MVP)

Week 1: schema + ingestion(1 source) + resolution v0 + `search_listings`/`get_property`/`get_price_history` over REST+MCP + Stripe metering.
Week 2: x402 middleware + guardrails + `get_market_stats`/`check_listing_freshness` + llms.txt/OpenAPI + directory submissions.
Week 3: `verify_claim` corpus-mode + attestation signing + eval harness (50 hand-labeled claims) + benchmark blog data pull.
