# Prompt for Coding Agent — Implement Attesta MVP

> Usage: paste into Claude Code at the repo root (empty dir), alongside `attesta-architecture.md`. Run milestone by milestone (M0→M5), reviewing between milestones. Keep `attesta-architecture.md` in the repo root — it is the authoritative design reference.

---

You are implementing **Attesta**, a B2A (business-to-agent) platform selling two metered products to AI agents: (1) provenance-grade Portuguese residential real-estate data, and (2) a claim-verification service returning signed JWS attestations. The full design is in `attesta-architecture.md` in this repo — read it first and treat it as authoritative. Where this prompt and the architecture doc conflict, the architecture doc wins; flag the conflict instead of silently choosing.

## Context and constraints

- Python 3.12, FastAPI, Pydantic v2, async throughout. Postgres 16 + pgvector. Deploy target: Railway (API service + 2 worker services from one Docker image, differentiated by start command). Snapshot store: Cloudflare R2 via boto3 S3 API.
- MCP: official `mcp` Python SDK, streamable HTTP transport mounted at `/mcp` on the same FastAPI app as REST.
- Payments: Stripe metered billing (usage records against subscription items) AND x402 (Coinbase CDP facilitator, USDC on Base). Read the current x402 spec and the facilitator API docs before implementing; the protocol is young — pin to the documented version and isolate it behind an interface (`app/payments/x402.py`) so spec drift is a one-file change.
- LLM calls: Anthropic API. `claude-haiku-4-5` class model for claim parsing and adjudication, JSON-schema-constrained outputs, temperature 0.
- Ingestion for MVP: **fixture-first** — bundled JSON in `tests/fixtures/` via `attesta-ingest --fixture`. Build the collector interface generic (`app/ingestion/base.py`) so each live source is a subclass. Optional Apify actor collectors for Idealista/Imovirtual when `APIFY_*` env is set (see ADR-008).
- Monorepo layout:

```
attesta/
  app/
    main.py            # FastAPI app factory; mounts REST + MCP
    config.py          # pydantic-settings; ALL config via env
    db/                # models (SQLAlchemy 2.0), migrations (alembic)
    ingestion/         # base collector, idealista_pt collector, pii_strip
    resolution/        # matcher, price_events, staleness
    serving/
      rest.py          # /v1/* routes
      mcp_server.py    # MCP tools registry
      tools.py         # shared tool implementations (single source of truth)
      descriptions.py  # tool descriptions (treat as product copy)
    payments/
      metering.py      # the single choke point (see §4.2 of architecture)
      stripe_rail.py
      x402.py
      guardrails.py    # rate limits, spend caps, idempotency
    verification/
      parse.py         # claim -> predicates
      retrieve.py      # evidence gathering (corpus + deep/live)
      adjudicate.py    # constrained LLM verdicts
      confidence.py    # deterministic scoring (documented formula)
      attest.py        # JWS signing, jwks endpoint
    workers/
      ingest_worker.py
      resolve_worker.py
  tests/
  evals/               # verification eval harness + labeled claims
  ops/                 # Dockerfile, railway.json, alembic.ini
  public/              # llms.txt, openapi export, attestation-spec.md
```

## Non-negotiable invariants (enforce in code and tests)

1. `snapshots` is append-only. No UPDATE or DELETE paths exist for it. Every derived fact carries `snapshot_id` lineage.
2. PII (names, phone numbers, emails) is stripped in the ingestion worker before any DB/R2 write. Include a test with seeded PII fixtures proving nothing leaks through.
3. Every priced execution — REST or MCP — passes through `payments/metering.py`. No endpoint may bypass it. Free-tier, Stripe, and x402 are branches inside it, not parallel paths.
4. The adjudicator LLM sees only retrieved evidence passed in the prompt. It must never be asked open-ended questions. Every CORROBORATED/CONTRADICTED verdict must cite ≥1 evidence hash or be downgraded to UNVERIFIABLE by post-validation code (not by trusting the model).
5. Responses never block on Stripe: usage records are queued (DB table) and pushed by a background flusher with retry. Idempotency by `request_id` end-to-end.
6. Raw API keys are never stored or logged — hash on receipt, compare hashes.
7. All secrets from env. Fail fast at startup on missing config with a clear message.

## Milestones — implement in order, stop after each for review

**M0 — Skeleton + CI.** Repo layout above, FastAPI app with `/healthz`, config, alembic setup, Dockerfile, docker-compose for local PG+pgvector, pytest wiring, GitHub Actions (lint: ruff; type-check: mypy strict on `app/`; tests). Acceptance: `docker compose up` + `pytest` green.

**M1 — Schema + ingestion.** Implement the full schema from architecture §3 via alembic. Ingestion worker: collector fetch → PII strip → R2 snapshot write → observations rows → diffing (price change, delist with re-check). Default `--fixture` mode reading bundled JSON fixtures (create ~40 realistic fake listings) so the pipeline is testable without external credentials. Optional live collectors (e.g. Apify actors) gated on env. Acceptance: fixture run populates snapshots/observations; second run with modified fixtures produces correct price_change and delisted diffs; PII test passes.

**M2 — Resolution + read API.** Matcher (geohash+attrs blocking, embedding similarity via a small local sentence-transformers model or pgvector-stored embeddings computed at ingest), property upsert, price_events derivation, days_on_market, staleness_score v0 (documented heuristic). REST `/v1/listings/search`, `/v1/properties/{id}`, `/v1/properties/{id}/history`, `/v1/market/stats`, `/v1/listings/freshness`. Acceptance: fixtures containing the same property on two "portals" resolve to one property with two sources; history endpoint shows the seeded price cut; unit tests on matcher edge cases (near-duplicates that must NOT merge).

**M3 — MCP + metering.** MCP server exposing the six tools (shared impls in `tools.py`; descriptions in `descriptions.py` — write them stating capability, coverage, freshness, price per call, and one example invocation each). Metering middleware: free tier counting, Stripe usage-record queue + flusher, x402 402-response + facilitator verify/settle, guardrails (per-key and per-wallet token bucket, daily caps, request_id idempotency). Stripe and the x402 facilitator must both be behind interfaces with fake implementations for tests. Acceptance: integration tests covering — keyed call decrements free tier then queues usage; keyless call returns 402 with valid payment spec; call with (faked) valid payment header executes and records payer; replayed request_id is not double-charged; cap exhaustion returns a clear, machine-readable error.

**M4 — Verification + attestations.** The five-stage pipeline (parse → resolve entity → retrieve → adjudicate → score) in corpus mode, plus deep mode behind a flag that live-fetches source URLs into new snapshots. JWS signing (ES256, `kid` support), `/.well-known/jwks.json`, `/v1/verify`, MCP `verify_claim`, attestations persisted. Post-validation layer enforcing invariant 4. Acceptance: eval harness in `evals/` with ≥50 labeled claims over the fixtures (mix of true, false, and unverifiable); report precision/recall per verdict class; a verification response's JWS validates against the jwks endpoint with standard libraries; a claim about a delisted property returns CONTRADICTED citing the delist snapshot.

**M5 — Discovery + ship.** `public/llms.txt`, exported OpenAPI, `public/attestation-spec.md` (the v0.1 spec from architecture §4.4, written for third-party consumers), Railway deploy config (3 services, health checks, release-phase migrations), README with 5-minute quickstart for an agent developer (MCP connect snippet + curl x402 walkthrough), and a `scripts/demo.py` that runs the Faro-apartment demo end-to-end against a deployed instance. Acceptance: fresh clone → README steps → working local demo; `railway.json` deploys cleanly.

## Working style

- After reading this prompt and `attesta-architecture.md`, produce a short build plan for the current milestone, then implement. Ask before deviating from the architecture doc.
- Tests are part of each milestone, not a final phase. Prefer integration tests over mock-heavy unit tests for the metering and verification paths.
- Type-hint everything; mypy strict must stay green.
- Commit per logical unit with imperative messages (`feat(metering): x402 payment spec on 402`).
- When a third-party spec is ambiguous (x402, MCP streamable HTTP), write down the assumption in `docs/decisions/` as a one-paragraph ADR and proceed.
- Do not implement: auth UI, admin dashboards, multi-region, Greece collectors, white-label — all explicitly out of MVP scope.
