"""REST /v1/* routes — all priced endpoints go through metering."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app import __version__
from app.db.session import get_db
from app.payments.metering import MeteringService
from app.serving.tools import CompsFilters, MarketStatsFilters, SearchFilters, ToolService

router = APIRouter(prefix="/v1")


class VerifyClaimRequest(BaseModel):
    claim: str
    depth: str = Field(default="corpus", pattern="^(corpus|deep)$")


def _request_id(request: Request) -> str:
    return request.headers.get("X-Request-Id", str(uuid.uuid4()))


@router.get("/healthz", tags=["meta"])
async def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@router.post("/listings/search")
async def search_listings(
    request: Request,
    body: SearchFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "search_listings",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    return await ToolService(db).search_listings(body)


@router.get("/properties/{property_id}")
async def get_property(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "get_property",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    result = await ToolService(db).get_property(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.get("/properties/{property_id}/history")
async def get_price_history(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "get_price_history",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    result = await ToolService(db).get_price_history(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.post("/market/stats")
async def get_market_stats(
    request: Request,
    body: MarketStatsFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "get_market_stats",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    return await ToolService(db).get_market_stats(body)


@router.post("/comps")
async def get_comps(
    request: Request,
    body: CompsFilters,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "get_comps",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    return await ToolService(db).get_comps(body)


@router.get("/listings/freshness/{property_id}")
async def check_listing_freshness(
    property_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "check_listing_freshness",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    result = await ToolService(db).check_listing_freshness(property_id)
    if not result:
        raise HTTPException(status_code=404, detail="Property not found")
    return result


@router.get("/evidence/{evidence_ref:path}")
async def get_evidence(
    evidence_ref: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    x_api_key: str | None = Header(default=None),
    x_payment: str | None = Header(default=None),
) -> dict:
    metering = MeteringService(db)
    await metering.authorize(
        "get_evidence",
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    from app.verification.evidence import EvidenceService

    result = await EvidenceService(db).resolve(evidence_ref)
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return result


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
    x_payment: str | None = Header(default=None),
) -> dict:
    tool = "verify_claim_deep" if body.depth == "deep" else "verify_claim_corpus"
    metering = MeteringService(db)
    ctx = await metering.authorize(
        tool,
        api_key=x_api_key,
        payment_header=x_payment,
        request_id=_request_id(request),
    )
    from app.verification.pipeline import VerificationPipeline

    return await VerificationPipeline(db).verify(
        body.claim,
        depth=body.depth,
        usage_event_id=ctx.usage_event_id,
    )
