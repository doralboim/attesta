import uuid

import pytest
from app.payments.metering import MeteringService
from app.payments.stripe_flusher import StripeUsageFlusher
from app.payments.stripe_rail import FakeStripeRail, StripeUsageRecord
from sqlalchemy.ext.asyncio import AsyncSession


class RecordingStripeRail(FakeStripeRail):
    async def queue_usage(self, record: StripeUsageRecord) -> None:
        await super().queue_usage(record)


@pytest.mark.asyncio
async def test_stripe_flusher_pushes_pending_usage(db_session: AsyncSession) -> None:
    from app.db.models import ApiKey, UsageEvent

    stripe = RecordingStripeRail()
    api_key = ApiKey(
        key_hash="hash123",
        stripe_customer_id="cus_test",
        stripe_subscription_item_id="si_test",
    )
    db_session.add(api_key)
    db_session.add(
        UsageEvent(
            rail="stripe",
            key_hash="hash123",
            tool="search_listings",
            price_eur=0.01,
            request_id=str(uuid.uuid4()),
            stripe_pushed=False,
        )
    )
    await db_session.commit()

    flusher = StripeUsageFlusher(stripe=stripe)
    pushed = await flusher.flush_once()
    assert pushed == 1
    assert len(stripe.records) == 1

    from app.db.models import UsageEvent
    from sqlalchemy import select

    event = (await db_session.execute(select(UsageEvent))).scalar_one()
    assert event.stripe_pushed is True


@pytest.mark.asyncio
async def test_metering_does_not_push_stripe_inline(db_session: AsyncSession) -> None:
    stripe = RecordingStripeRail()
    metering = MeteringService(db_session, stripe=stripe)
    await metering.authorize(
        "search_listings",
        api_key="dev-key-change-me",
        request_id=str(uuid.uuid4()),
    )
    assert stripe.records == []
