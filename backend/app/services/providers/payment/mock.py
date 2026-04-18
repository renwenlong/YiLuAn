"""Instant-success mock provider for dev / test."""

from __future__ import annotations

import uuid
from typing import Any

from app.services.providers.payment.base import (
    OrderDTO,
    PaymentProvider,
    RefundDTO,
)


class MockPaymentProvider(PaymentProvider):
    """No external calls; pretends every request succeeds immediately."""

    name = "mock"

    async def create_order(self, order: OrderDTO) -> dict[str, Any]:
        fake_trade = f"MOCK_{uuid.uuid4().hex[:16].upper()}"
        return {
            "trade_no": fake_trade,
            "prepay_id": f"mock_prepay_{fake_trade}",
            "status": "success",
        }

    async def refund(self, refund: RefundDTO) -> dict[str, Any]:
        return {
            "refund_id": refund.refund_id,
            "status": "success",
        }

    async def verify_callback(
        self, headers: dict, body: bytes
    ) -> dict[str, Any]:
        # Try to parse the body so the endpoint can route on the embedded
        # trade_no / out_trade_no, but always advertise verified=True so
        # callers in dev/test see a stable shape.
        import json as _json

        parsed: dict[str, Any] = {}
        try:
            decoded = _json.loads(body) if body else {}
            if isinstance(decoded, dict):
                parsed = decoded
        except Exception:
            parsed = {}
        parsed.setdefault("verified", True)
        return parsed

    async def query(self, order: OrderDTO) -> dict[str, Any]:
        return {
            "out_trade_no": order.order_number,
            "trade_state": "SUCCESS",
        }
