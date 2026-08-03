"""Rate limits, spend caps, idempotency."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UsageEvent


class Guardrails:
    def __init__(
        self,
        session: AsyncSession,
        rate_limit_per_minute: int = 60,
        daily_spend_cap_eur: float = 50.0,
    ) -> None:
        self.session = session
        self.rate_limit_per_minute = rate_limit_per_minute
        self.daily_spend_cap_eur = daily_spend_cap_eur

    async def check_rate_limit(self, identifier: str) -> bool:
        since = datetime.now(UTC) - timedelta(minutes=1)
        count = await self.session.scalar(
            select(func.count())
            .select_from(UsageEvent)
            .where(UsageEvent.occurred_at >= since)
            .where((UsageEvent.key_hash == identifier) | (UsageEvent.payer_address == identifier))
        )
        return (count or 0) < self.rate_limit_per_minute

    async def check_daily_cap(self, identifier: str) -> bool:
        since = datetime.now(UTC) - timedelta(days=1)
        total = await self.session.scalar(
            select(func.coalesce(func.sum(UsageEvent.price_eur), 0))
            .where(UsageEvent.occurred_at >= since)
            .where((UsageEvent.key_hash == identifier) | (UsageEvent.payer_address == identifier))
        )
        return float(total or 0) < self.daily_spend_cap_eur

    async def is_duplicate_request(self, request_id: str) -> bool:
        existing = await self.session.scalar(select(UsageEvent.id).where(UsageEvent.request_id == request_id))
        return existing is not None
