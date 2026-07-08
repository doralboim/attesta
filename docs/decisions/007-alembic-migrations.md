# ADR-007: Alembic migrations for production schema

**Status:** Accepted (2026-07-05)

**Context:** Production Postgres must not rely on `Base.metadata.create_all()` at startup. Schema changes (e.g. `consecutive_ingest_misses`) need versioned migrations.

**Decision:** Initial migration `0001_initial_schema` creates the full pgvector-enabled schema. Dev/test still auto-create via lifespan for fast local runs. Railway runs `alembic upgrade head` as release command. `make migrate` for local Postgres after `make db-up`.

**Consequences:** SQLite tests bypass Alembic (conftest drop/create). Production deploys must run migrations before traffic.
