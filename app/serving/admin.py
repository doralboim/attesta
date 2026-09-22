"""Internal ops API — not a dashboard, not in the public OpenAPI schema."""

from __future__ import annotations

import secrets
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.payments.pricing import PricingService, known_tools

router = APIRouter(prefix="/internal", include_in_schema=False)


class PriceUpdate(BaseModel):
    price_eur: str


class PricesUpdate(BaseModel):
    prices: dict[str, str]


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    settings = get_settings()
    if not settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin API not configured",
        )
    if not x_admin_token or not secrets.compare_digest(x_admin_token, settings.admin_api_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token")


@router.get("/pricing")
async def list_pricing(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    prices = await PricingService(db).list_prices()
    return {"prices": prices}


@router.patch("/pricing")
async def update_pricing_bulk(
    body: PricesUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    updated: dict[str, str] = {}
    for tool, price_eur in body.prices.items():
        if tool not in known_tools():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool: {tool}")
        try:
            amount = Decimal(price_eur)
        except InvalidOperation as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid price_eur") from exc
        try:
            await PricingService(db).set_price(tool, amount)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        updated[tool] = str(amount)
    return {"prices": updated}


@router.patch("/pricing/{tool}")
async def update_pricing(
    tool: str,
    body: PriceUpdate,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin),
) -> dict:
    if tool not in known_tools():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool: {tool}")
    try:
        amount = Decimal(body.price_eur)
    except InvalidOperation as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid price_eur") from exc
    try:
        await PricingService(db).set_price(tool, amount)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"tool": tool, "price_eur": str(amount)}
