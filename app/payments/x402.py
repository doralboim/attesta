"""x402 rail — isolated behind interface for spec drift."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()


@dataclass
class PaymentSpec:
    scheme: str
    network: str
    asset: str
    amount: str
    pay_to: str
    resource: str
    valid_until: int


@dataclass
class PaymentVerification:
    valid: bool
    payer_address: str | None
    receipt: dict | None


class X402Rail(ABC):
    @abstractmethod
    def build_payment_spec(self, tool: str, price_eur: Decimal, resource: str) -> PaymentSpec:
        pass

    @abstractmethod
    async def verify_payment(self, payment_header: str) -> PaymentVerification:
        pass


class FakeX402Rail(X402Rail):
    VALID_HEADER = "fake-payment-valid"

    def __init__(
        self,
        *,
        pay_to: str = "0xFakeAddress",
        network: str = "eip155:84532",
    ) -> None:
        self.pay_to = pay_to
        self.network = network

    def build_payment_spec(self, tool: str, price_eur: Decimal, resource: str) -> PaymentSpec:
        return PaymentSpec(
            scheme="exact",
            network=self.network,
            asset="USDC",
            amount=str(price_eur),
            pay_to=self.pay_to,
            resource=resource,
            valid_until=9999999999,
        )

    async def verify_payment(self, payment_header: str) -> PaymentVerification:
        if payment_header == self.VALID_HEADER:
            return PaymentVerification(
                valid=True,
                payer_address="0xTestWallet",
                receipt={"fake": True},
            )
        return PaymentVerification(valid=False, payer_address=None, receipt=None)


class LiveX402Rail(X402Rail):
    """Verify and settle via Coinbase CDP / x402 facilitator HTTP API."""

    def __init__(
        self,
        *,
        facilitator_url: str,
        pay_to: str,
        network: str,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.facilitator_url = facilitator_url.rstrip("/")
        self.pay_to = pay_to
        self.network = network
        self.timeout_seconds = timeout_seconds

    def build_payment_spec(self, tool: str, price_eur: Decimal, resource: str) -> PaymentSpec:
        import time

        return PaymentSpec(
            scheme="exact",
            network=self.network,
            asset="USDC",
            amount=str(price_eur),
            pay_to=self.pay_to,
            resource=resource,
            valid_until=int(time.time()) + 300,
        )

    async def verify_payment(self, payment_header: str) -> PaymentVerification:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            verify_body = {
                "payment": payment_header,
                "network": self.network,
                "payTo": self.pay_to,
            }
            verify_resp = await client.post(f"{self.facilitator_url}/verify", json=verify_body)
            if verify_resp.status_code != 200:
                logger.warning("x402_verify_failed", status=verify_resp.status_code)
                return PaymentVerification(valid=False, payer_address=None, receipt=None)

            verify_data = verify_resp.json()
            if not verify_data.get("valid", verify_data.get("isValid")):
                return PaymentVerification(valid=False, payer_address=None, receipt=verify_data)

            settle_resp = await client.post(
                f"{self.facilitator_url}/settle",
                json={"payment": payment_header, "network": self.network},
            )
            if settle_resp.status_code != 200:
                logger.warning("x402_settle_failed", status=settle_resp.status_code)
                return PaymentVerification(valid=False, payer_address=None, receipt=verify_data)

            settle_data: dict[str, Any] = settle_resp.json()
            payer = (
                settle_data.get("payer")
                or settle_data.get("payerAddress")
                or verify_data.get("payer")
                or verify_data.get("payerAddress")
            )
            receipt = {"verify": verify_data, "settle": settle_data}
            return PaymentVerification(valid=True, payer_address=payer, receipt=receipt)
