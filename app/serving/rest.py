"""REST /v1/* routes — all priced endpoints go through metering."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.config import get_settings
from app.db.models import ApiKey
from app.db.session import get_db
from app.ingestion.pii_strip import hash_api_key
from app.payments.metering import MeteringContext, MeteringService
from app.payments.x402 import encode_payment_response
from app.serving.lazy_corpus import lazy_corpus
from app.serving.tools import CompsFilters, MarketStatsFilters, SearchFilters, ToolService

router = APIRouter(prefix="/v1")

MINT_RATE_LIMIT_PER_HOUR = 20


class VerifyClaimRequest(BaseModel):
    claim: str | None = None
    url: str | None = None
    depth: str = Field(default="corpus", pattern="^(corpus|deep)$")

    @model_validator(mode="after")
    def exactly_one_subject(self) -> VerifyClaimRequest:
        if bool(self.claim) == bool(self.url):
            raise ValueError("Provide exactly one of claim or url")
        return self


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


def _payment_header(
    payment_signature: str | None = Header(default=None, alias="PAYMENT-SIGNATURE"),
    x_payment: str | None = Header(default=None),
) -> str | None:
    return payment_signature or x_payment


def _with_payment_response(body: dict, ctx: MeteringContext) -> JSONResponse:
    headers = {}
    if ctx.rail == "x402":
        headers["PAYMENT-RESPONSE"] = encode_payment_response(
            success=True,
            network="",
            payer=ctx.payer_address,
            receipt=ctx.x402_receipt,
        )
    return JSONResponse(content=body, headers=headers)


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@router.post("/keys", tags=["meta"])
async def mint_api_key(db: AsyncSession = Depends(get_db)) -> dict:
    """Mint a free-tier API key (unmetered). Raw key is returned once."""
    settings = get_settings()
    hour_ago = datetime.now(UTC) - timedelta(hours=1)
    recent = await db.scalar(
        select(func.count()).select_from(ApiKey).where(ApiKey.created_at >= hour_ago)
    )
    if (recent or 0) >= MINT_RATE_LIMIT_PER_HOUR:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "mint_rate_limit_exceeded"},
        )

    raw_key = secrets.token_urlsafe(32)
    monthly_free = settings.free_tier_monthly_calls
    db.add(
        ApiKey(
            key_hash=hash_api_key(raw_key),
            plan="metered",
            monthly_free_calls=monthly_free,
            is_active=True,
        )
    )
    await db.commit()
    return {"api_key": raw_key, "monthly_free_calls": monthly_free}


@router.post("/listings/search")
async def search_listings(
    request: Request,
    body: SearchFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "search_listings",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    result = await lazy_corpus.begin_search(db, body)
    return _with_payment_response(result, ctx)


def _sse(data: dict) -> str:
    return f"event: coverage\ndata: {json.dumps(data)}\n\n"


async def _allow_ingest_events(db: AsyncSession, api_key: str | None) -> None:
    """Confirm the caller without a second metered charge."""
    settings = get_settings()
    if settings.environment in ("development", "test"):
        return
    if not api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "api_key_required"})
    row = await db.scalar(
        select(ApiKey).where(ApiKey.key_hash == hash_api_key(api_key), ApiKey.is_active.is_(True))
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"code": "invalid_api_key"})


async def _ingest_event_stream(job_id: str):
    job = lazy_corpus.jobs.get(job_id)
    if job is None:
        yield _sse({"status": "unavailable", "message": "Unknown ingest job.", "job_id": job_id})
        return
    yield _sse({"status": "updating", "message": job.message, "job_id": job.id})
    if job.payload is not None:
        yield _sse(job.payload)
        return
    queue = job.subscribe()
    while True:
        event = await queue.get()
        if "listings" not in event:
            continue
        yield _sse(event)
        return


@router.get("/listings/ingest/{job_id}/events")
async def ingest_events(
    job_id: str,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
) -> StreamingResponse:
    await _allow_ingest_events(db, x_api_key)
    return StreamingResponse(
        _ingest_event_stream(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/properties/{property_id}")
async def get_property(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "get_property",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    result = await ToolService(db).get_property(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return _with_payment_response(result, ctx)


@router.get("/properties/{property_id}/history")
async def get_price_history(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "get_price_history",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    result = await ToolService(db).get_price_history(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return _with_payment_response(result, ctx)


@router.post("/market/stats")
async def get_market_stats(
    request: Request,
    body: MarketStatsFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "get_market_stats",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    return _with_payment_response(await ToolService(db).get_market_stats(body), ctx)


@router.post("/comps")
async def get_comps(
    request: Request,
    body: CompsFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "get_comps",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    return _with_payment_response(await ToolService(db).get_comps(body), ctx)


@router.get("/listings/freshness/{property_id}")
async def check_listing_freshness(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "check_listing_freshness",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    result = await ToolService(db).check_listing_freshness(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return _with_payment_response(result, ctx)


@router.get("/evidence/{evidence_ref:path}")
async def get_evidence(
    evidence_ref: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    metering = MeteringService(db)
    ctx = await metering.authorize(
        "get_evidence",
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    from app.verification.evidence import EvidenceService

    result = await EvidenceService(db).resolve(evidence_ref)
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return _with_payment_response(result, ctx)


@router.post("/verify/jws/validate")
async def validate_jws(body: dict) -> dict:
    """Public endpoint — verify a JWS token against our JWKS (no metering)."""
    token = body.get("jws") or body.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Missing jws field")
    from app.verification.attest import AttestationSigner

    try:
        payload = AttestationSigner().verify(token)
        return {"valid": True, "payload": payload}
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


@router.post("/verify")
async def verify_claim(
    request: Request,
    body: VerifyClaimRequest,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    payment_header: str | None = Depends(_payment_header),
) -> JSONResponse:
    if body.url:
        tool = "verify_url"
    elif body.depth == "deep":
        tool = "verify_claim_deep"
    else:
        tool = "verify_claim_corpus"
    metering = MeteringService(db)
    ctx = await metering.authorize(
        tool,
        api_key=x_api_key,
        payment_header=payment_header,
        request_id=_request_id(request),
    )
    from app.verification.pipeline import VerificationPipeline

    pipeline = VerificationPipeline(db)
    if body.url:
        result = await pipeline.verify_url(body.url, usage_event_id=ctx.usage_event_id)
    else:
        result = await pipeline.verify(
            body.claim or "",
            depth=body.depth,
            usage_event_id=ctx.usage_event_id,
        )
    return _with_payment_response(result, ctx)
