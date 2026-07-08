# ADR-004: SQLite for unit tests, Postgres in CI

**Status:** Accepted (2026-07-05)

**Context:** Fast feedback locally; production uses Postgres + pgvector.

**Decision:** Tests default to `sqlite+aiosqlite`. CI runs full suite against Postgres pgvector container. JSON columns use SQLAlchemy `JSON().with_variant(JSONB, "postgresql")`.

**Consequences:** Embedding/vector features degrade to Text on SQLite; resolution tests use attribute+geo matching only.
