"""FastAPI app factory — mounts REST + MCP + JWKS."""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager

import structlog
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from app import __version__
from app.config import get_settings
from app.db.models import Base
from app.db.session import engine
from app.serving import mcp_server
from app.serving.rest import router as rest_router
from app.verification.attest import AttestationSigner

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.payments.stripe_flusher import StripeUsageFlusher

    settings = get_settings()
    flusher = StripeUsageFlusher()
    # Dev/test: auto-create schema. Production: run `alembic upgrade head` before deploy.
    if settings.environment in ("development", "test"):
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await flusher.start()
    try:
        yield
    finally:
        await flusher.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
    )

    app = FastAPI(
        title="Attesta",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(rest_router)

    @app.get("/healthz")
    async def root_healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/llms.txt", response_class=PlainTextResponse)
    async def llms_txt() -> str:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "public" / "llms.txt"
        body = path.read_text(encoding="utf-8")
        return body.replace("http://localhost:8000", settings.public_base_url.rstrip("/"))

    @app.get("/.well-known/mcp/server-card.json")
    async def mcp_server_card() -> JSONResponse:
        from pathlib import Path

        path = Path(__file__).resolve().parents[1] / "public" / "server-card.json"
        return JSONResponse(content=json.loads(path.read_text(encoding="utf-8")))

    @app.get("/.well-known/jwks.json")
    async def jwks() -> JSONResponse:
        return JSONResponse(AttestationSigner().public_jwks())

    mcp_app = mcp_server.mcp.http_app(
        path="/", transport="streamable-http", stateless_http=True
    )
    app.mount("/mcp", mcp_app)

    return app


app = create_app()


def cli() -> None:
    import os

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=get_settings().environment == "development")
