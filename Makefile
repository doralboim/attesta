.PHONY: install dev test lint typecheck ci docker-up ingest resolve migrate migrate-down db-up demo eval openapi

install:
	/opt/homebrew/bin/python3.14 -m venv .venv || python3 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -e ".[dev]"

dev:
	ENVIRONMENT=development .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

test:
	ENVIRONMENT=test DATABASE_URL=sqlite+aiosqlite:///./test_attesta.db .venv/bin/pytest -q

lint:
	.venv/bin/ruff check app tests
	.venv/bin/ruff format --check app tests

typecheck:
	.venv/bin/mypy app

ci: lint typecheck test

db-up:
	docker compose up -d db

migrate:
	.venv/bin/alembic upgrade head

migrate-down:
	.venv/bin/alembic downgrade -1

migrate-new:
	@test -n "$(MSG)" || (echo 'Usage: make migrate-new MSG="describe change"' && exit 1)
	.venv/bin/alembic revision --autogenerate -m "$(MSG)"

docker-up:
	docker compose up --build

ingest:
	.venv/bin/attesta-ingest --fixture

resolve:
	.venv/bin/attesta-resolve

eval:
	ENVIRONMENT=test DATABASE_URL=sqlite+aiosqlite:///./eval_attesta.db .venv/bin/python evals/run_eval.py

demo:
	.venv/bin/python scripts/demo.py

openapi:
	.venv/bin/python scripts/export_openapi.py
