from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.payments.x402 import LiveX402Rail


@pytest.mark.asyncio
async def test_live_x402_verify_and_settle() -> None:
    rail = LiveX402Rail(
        facilitator_url="https://facilitator.test",
        pay_to="0xMerchant",
        network="eip155:84532",
    )

    verify_resp = MagicMock(status_code=200)
    verify_resp.json.return_value = {"valid": True, "payerAddress": "0xPayer"}
    settle_resp = MagicMock(status_code=200)
    settle_resp.json.return_value = {"success": True, "payer": "0xPayer"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[verify_resp, settle_resp])
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None

    with patch("app.payments.x402.httpx.AsyncClient", return_value=mock_client):
        result = await rail.verify_payment("payment-header-token")

    assert result.valid is True
    assert result.payer_address == "0xPayer"
    assert result.receipt is not None
