# Attesta verify matrix

## Local (before `gh pr create`)

Always, from the worktree:

```bash
ENVIRONMENT=test DATABASE_URL=sqlite+aiosqlite:///./test_attesta.db \
  PYTHONPATH=. .venv/bin/pytest -q
.venv/bin/ruff check app tests
```

| Paths | Extra |
|-------|--------|
| `app/verification/**`, `evals/**` | `make eval` if eval harness is touched |
| `alembic/versions/**` | Confirm revision chain; do not apply to production Neon from a feat branch unless the task is the migration itself |

Use the worktree's `.venv` if present; otherwise the primary clone `.venv` with `PYTHONPATH` set to the worktree.

## Post-deploy (after merge to `main`)

| Paths | Check |
|-------|--------|
| `app/**`, `ops/**` | `curl -fsS https://api-production-d9143.up.railway.app/healthz` |
| `app/verification/**`, `public/attestation-spec.md` | `GET https://api-production-d9143.up.railway.app/llms.txt` contains `verify@0.2` or current method string |
| payments / metering | Do **not** flip `X402_ENABLED` as a health check |

If Railway has not redeployed yet, wait for the deploy from `main` then retry once.
