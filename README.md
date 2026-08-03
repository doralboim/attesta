# Attesta

B2A platform: provenance-grade Portugal residential property data + signed JWS verification for AI agents.

**Authoritative docs:** `attesta-architecture.md` · `attesta-agent-prompt.md`

## Quick start

```bash
make install
cp .env.example .env
make db-up                 # Postgres + pgvector
make migrate               # apply Alembic migrations
make dev                   # API at :8000
```

| Endpoint | URL |
|----------|-----|
| Health | `/healthz` |
| REST API | `/docs` |
| MCP | `/mcp` |
| JWKS | `/.well-known/jwks.json` |
| Agent discovery | `/llms.txt` |

## Pipeline (local)

```bash
make ingest    # attesta-ingest --fixture (bundled JSON corpus)
make resolve   # attesta-resolve
make test
```

## Ingestion

**Default:** bundled fixtures in `tests/fixtures/` — no external scraper credentials needed.

```bash
make ingest                              # same as attesta-ingest --fixture
attesta-ingest --fixture                 # explicit
attesta-ingest --source idealista_pt     # optional: Apify actor (needs APIFY_* in .env)
attesta-ingest --source imovirtual       # optional: Apify actor
```

Live portal collectors implement `app/ingestion/base.py` (`BaseCollector`). Apify-backed Idealista/Imovirtual collectors ship as optional plugins; add a new source by subclassing, not refactoring the pipeline. See `docs/decisions/008-fixture-first-ingestion.md`.

To grow production corpus: pick a collector strategy (build Apify actors, direct HTTP, licensed feed, CSV import), wire env, and schedule the ingest worker on Railway.

## CI

GitHub Actions runs ruff, mypy (advisory), pytest on SQLite + Postgres.

## Decisions

Architecture Decision Records: `docs/decisions/`  
Cursor rules: `.cursor/rules/`

## Milestone status

- [x] M0 — Skeleton, CI, docker-compose, alembic scaffold
- [x] M1 — Schema, ingestion worker, fixtures, PII tests
- [x] M2 — Resolution matcher, read API
- [x] M3 — MCP tools, metering choke point, guardrails
- [x] M4 — Verification pipeline, JWS/JWKS, evidence API, eval harness (62 claims), attestation spec
- [x] M5 — Railway 3-service config, demo + verify scripts, OpenAPI export

## Verification

```bash
make eval                    # 62 labeled claims, 75% threshold
python scripts/verify_jws.py <jws> --local
python scripts/demo.py       # E2E against local API
make openapi                 # writes public/openapi.json
```

### LLM (optional, provider-agnostic via LiteLLM)

Set `LLM_ENABLED=true` and configure models + prompt file paths in `.env` (see `.env.example`).  
Uses [LiteLLM](https://docs.litellm.ai/) — point `LLM_PARSE_MODEL` / `LLM_ADJUDICATE_MODEL` at **any** supported provider (`anthropic/`, `openai/`, `gemini/`, `azure/`, `groq/`, etc.).  
Provider API keys follow LiteLLM env conventions — set only the key(s) for your chosen provider(s).  
See `distribution/llm-providers.md` for examples and cost estimates.

Attestation spec: `public/attestation-spec.md`  
Market data contract (stats/comps envelopes): `public/market-data-contract.md`
