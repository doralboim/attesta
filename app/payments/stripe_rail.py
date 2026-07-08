"""Stripe rail — interface + fake for tests."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class StripeUsageRecord:
    customer_id: str
    subscription_item_id: str
    quantity: int
    tool: str


class StripeRail(ABC):
    @abstractmethod
    async def queue_usage(self, record: StripeUsageRecord) -> None:
        pass


class FakeStripeRail(StripeRail):
    def __init__(self) -> None:
        self.records: list[StripeUsageRecord] = []

    async def queue_usage(self, record: StripeUsageRecord) -> None:
        self.records.append(record)


class LiveStripeRail(StripeRail):
    def __init__(self, secret_key: str, meter_event_name: str) -> None:
        import stripe

        stripe.api_key = secret_key
        self.stripe = stripe
        self.meter_event_name = meter_event_name

    async def queue_usage(self, record: StripeUsageRecord) -> None:
        self.stripe.billing.MeterEvent.create(
            event_name=self.meter_event_name,
            payload={
                "stripe_customer_id": record.customer_id,
                "value": str(record.quantity),
                "tool": record.tool,
            },
        )
