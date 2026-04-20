"""
E2E: Order timeout refund → wallet balance (happy path).

Scenario: patient creates order → pays → order expires (timeout, no companion accepts)
→ check_expired triggers auto-refund → wallet transactions show refund entry.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import update

from app.models.order import Order
from tests.conftest import test_session_factory


async def _create_order(client, hospital_id):
    resp = await client.post(
        "/api/v1/orders",
        json={
            "service_type": "full_accompany",
            "hospital_id": str(hospital_id),
            "appointment_date": "2026-06-01",
            "appointment_time": "09:00",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
class TestRefundToWalletE2E:
    async def test_expired_order_refund_to_wallet(
        self, authenticated_client, seed_hospital
    ):
        """Happy path: create → pay → expire → auto-refund → wallet has refund entry."""
        hospital = await seed_hospital()

        # 1. Create order
        order = await _create_order(authenticated_client, hospital.id)
        order_id = order["id"]
        assert order["status"] == "created"
        assert order["price"] == 299.0

        # 2. Pay
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/pay")
        assert resp.status_code == 200
        assert resp.json()["mock_success"] is True

        resp = await authenticated_client.get(f"/api/v1/orders/{order_id}")
        assert resp.json()["payment_status"] == "paid"

        # 3. Simulate timeout: set expires_at to the past via DB
        async with test_session_factory() as session:
            await session.execute(
                update(Order)
                .where(Order.id == UUID(order_id))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
            )
            await session.commit()

        # 4. Trigger expiry check via API
        resp = await authenticated_client.post("/api/v1/orders/check-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cancelled_count"] >= 1
        assert order_id in data["cancelled_order_ids"]

        # 5. Assert order status = expired
        resp = await authenticated_client.get(f"/api/v1/orders/{order_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["status"] == "expired"

        # 6. Assert payment_status = refunded
        assert detail["payment_status"] == "refunded"

        # 7. Assert wallet transactions contain refund entry with full amount
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        refunds = [t for t in items if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 299.0  # full refund for expired order
        assert refunds[0]["status"] == "success"

        # 8. Assert pay record also exists
        pays = [t for t in items if t["payment_type"] == "pay"]
        assert len(pays) == 1
        assert pays[0]["amount"] == 299.0
