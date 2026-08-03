"""Background Stripe usage flusher — never block API responses on Stripe."""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.db.models import ApiKey, UsageEvent
from app.db.session import async_session_factory
from app.payments.stripe_rail import LiveStripeRail, StripeRail, StripeUsageRecord

logger = structlog.get_logger()


class StripeUsageFlusher:
    def __init__(self, stripe: StripeRail | None = None) -> None:
        settings = get_settings()
        self.interval = settings.stripe_flush_interval_seconds
        if stripe is not None:
            self.stripe = stripe
        elif settings.stripe_secret_key:
            self.stripe = LiveStripeRail(
                settings.stripe_secret_key,
                settings.stripe_meter_event_name,
            )
        else:
            self.stripe = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if not self.stripe or self._task:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("stripe_flusher_started", interval_seconds=self.interval)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.flush_once()
            except Exception:
                logger.exception("stripe_flush_error")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except TimeoutError:
                continue

    async def flush_once(self) -> int:
        if not self.stripe:
            return 0

        pushed = 0
        async with async_session_factory() as session:
            pending = (
                (
                    await session.execute(
                        select(UsageEvent)
                        .where(UsageEvent.rail == "stripe")
                        .where(UsageEvent.stripe_pushed.is_(False))
                        .order_by(UsageEvent.id)
                        .limit(100)
                    )
                )
                .scalars()
                .all()
            )

            for event in pending:
                if not event.key_hash:
                    continue
                api_key = await session.get(ApiKey, event.key_hash)
                if not api_key or not api_key.stripe_customer_id or not api_key.stripe_subscription_item_id:
                    continue
                await self.stripe.queue_usage(
                    StripeUsageRecord(
                        customer_id=api_key.stripe_customer_id,
                        subscription_item_id=api_key.stripe_subscription_item_id,
                        quantity=1,
                        tool=event.tool,
                    )
                )
                event.stripe_pushed = True
                pushed += 1

            if pushed:
                await session.commit()
                logger.info("stripe_flush_complete", pushed=pushed)
        return pushed
