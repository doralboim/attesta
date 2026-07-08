"""Single metering choke point — every priced REST/MCP call passes through here."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import ApiKey, UsageEvent
from app.ingestion.pii_strip import hash_api_key
from app.payments.guardrails import Guardrails
from app.payments.pricing import price_for_tool
from app.payments.stripe_rail import FakeStripeRail, LiveStripeRail, StripeRail
from app.payments.x402 import FakeX402Rail, LiveX402Rail, PaymentSpec, X402Rail


@dataclass
class MeteringContext:
    rail: str
    key_hash: str | None
    payer_address: str | None
    request_id: str
    tool: str
    price_eur: Decimal
    usage_event_id: int | None = None


class MeteringService:
    def _default_x402(self) -> X402Rail:
        if self.settings.x402_enabled and self.settings.x402_evm_address:
            return LiveX402Rail(
                facilitator_url=self.settings.x402_facilitator_url,
                pay_to=self.settings.x402_evm_address,
                network=self.settings.x402_network,
            )
        return FakeX402Rail(
            pay_to=self.settings.x402_evm_address or "0xFakeAddress",
            network=self.settings.x402_network,
        )

    def __init__(
        self,
        session: AsyncSession,
        stripe: StripeRail | None = None,
        x402: X402Rail | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.stripe = stripe or self._default_stripe()
        self.x402 = x402 or self._default_x402()
        self.guardrails = Guardrails(
            session,
            rate_limit_per_minute=self.settings.rate_limit_per_minute,
            daily_spend_cap_eur=self.settings.daily_spend_cap_eur,
        )

    def _default_stripe(self) -> StripeRail:
        if self.settings.stripe_secret_key:
            return LiveStripeRail(
                self.settings.stripe_secret_key, self.settings.stripe_meter_event_name
            )
        return FakeStripeRail()

    async def authorize(
        self,
        tool: str,
        *,
        api_key: str | None = None,
        payment_header: str | None = None,
        request_id: str | None = None,
    ) -> MeteringContext:
        rid = request_id or str(uuid.uuid4())
        price = price_for_tool(tool)

        if await self.guardrails.is_duplicate_request(rid):
            existing = await self.session.scalar(
                select(UsageEvent).where(UsageEvent.request_id == rid)
            )
            if existing:
                return MeteringContext(
                    rail=existing.rail,
                    key_hash=existing.key_hash,
                    payer_address=existing.payer_address,
                    request_id=rid,
                    tool=tool,
                    price_eur=Decimal(str(existing.price_eur)),
                    usage_event_id=existing.id,
                )

        identifier: str | None = None

        if api_key:
            ctx = await self._authorize_api_key(api_key, tool, price, rid)
            identifier = ctx.key_hash
        elif payment_header:
            ctx = await self._authorize_x402(payment_header, tool, price, rid)
            identifier = ctx.payer_address
        elif self.settings.environment in ("development", "test"):
            ctx = MeteringContext(
                rail="dev_bypass",
                key_hash=None,
                payer_address=None,
                request_id=rid,
                tool=tool,
                price_eur=price,
            )
        else:
            spec = self.x402.build_payment_spec(tool, price, resource=f"/v1/{tool}")
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "message": "Payment required",
                    "payment_spec": spec.__dict__,
                },
            )

        if identifier and not await self.guardrails.check_rate_limit(identifier):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"code": "rate_limit_exceeded"},
            )
        if identifier and not await self.guardrails.check_daily_cap(identifier):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={"code": "daily_spend_cap_exceeded"},
            )

        await self._record_usage(ctx)
        return ctx

    async def _authorize_api_key(
        self, raw_key: str, tool: str, price: Decimal, request_id: str
    ) -> MeteringContext:
        key_hash = hash_api_key(raw_key)
        api_key = await self.session.get(ApiKey, key_hash)
        if not api_key and raw_key == self.settings.bootstrap_api_key:
            api_key = ApiKey(key_hash=key_hash, monthly_free_calls=self.settings.free_tier_monthly_calls)
            self.session.add(api_key)
            await self.session.flush()
        if not api_key or not api_key.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

        rail = "free" if await self._has_free_tier_remaining(key_hash, api_key.monthly_free_calls) else "stripe"
        return MeteringContext(
            rail=rail,
            key_hash=key_hash,
            payer_address=None,
            request_id=request_id,
            tool=tool,
            price_eur=price if rail == "stripe" else Decimal("0"),
        )

    async def _authorize_x402(
        self, payment_header: str, tool: str, price: Decimal, request_id: str
    ) -> MeteringContext:
        verification = await self.x402.verify_payment(payment_header)
        if not verification.valid:
            raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail="Invalid payment")
        return MeteringContext(
            rail="x402",
            key_hash=None,
            payer_address=verification.payer_address,
            request_id=request_id,
            tool=tool,
            price_eur=price,
        )

    async def _has_free_tier_remaining(self, key_hash: str, monthly_free: int) -> bool:
        month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        used = await self.session.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(UsageEvent.key_hash == key_hash)
            .where(UsageEvent.rail == "free")
            .where(UsageEvent.occurred_at >= month_start)
        )
        return (used or 0) < monthly_free

    async def _record_usage(self, ctx: MeteringContext) -> None:
        event = UsageEvent(
            rail=ctx.rail,
            key_hash=ctx.key_hash,
            payer_address=ctx.payer_address,
            tool=ctx.tool,
            price_eur=float(ctx.price_eur),
            request_id=ctx.request_id,
            stripe_pushed=False,
        )
        self.session.add(event)
        await self.session.flush()
        ctx.usage_event_id = event.id

        await self.session.commit()

    def payment_spec_for_tool(self, tool: str) -> PaymentSpec:
        return self.x402.build_payment_spec(tool, price_for_tool(tool), resource=f"/v1/{tool}")
