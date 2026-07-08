# ADR-008: Fixture-first ingestion, pluggable live collectors

**Status:** Accepted (2026-07-05)

**Context:** Early planning docs assumed a pre-existing scraping stack (“re-radar”) and Apify actors. That infrastructure does not exist. The pipeline must run end-to-end in CI and local dev without external scraper credentials.

**Decision:** Default ingestion source is bundled JSON fixtures (`attesta-ingest --fixture`). Live portal data uses the `BaseCollector` interface — implement a subclass per source. Apify actor runners (`idealista_pt`, `imovirtual`) are optional plugins gated on `APIFY_*` env vars; they are not assumed at deploy time.

**Consequences:** `make ingest` and the ingest worker CLI default to `--fixture`. Production corpus growth requires explicitly choosing and wiring a collector (Apify, direct HTTP, licensed feed, CSV import, etc.). Docs no longer reference re-radar or “already-built” scrapers.
