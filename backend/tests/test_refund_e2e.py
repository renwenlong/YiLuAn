"""
E2E: Order refund → wallet balance.

Scenarios:
1. Happy path: order expires → full auto-refund → wallet credit
2. Partial refund: in_progress order cancelled by patient → 50% refund
3. Idempotency: duplicate refund attempt on already-refunded order → no double credit
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import update

from app.core.security import create_access_token
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

    async def test_partial_refund_to_wallet(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_companion_profile,
    ):
        """Cancel in_progress order → 50% refund → wallet shows partial amount."""
        from app.models.user import UserRole

        hospital = await seed_hospital()

        # Create patient and companion users with separate tokens
        patient = await seed_user(phone="13800138000", role=UserRole.patient)
        patient_token = create_access_token({"sub": str(patient.id), "role": "patient"})

        companion = await seed_user(phone="13700137000", role=UserRole.companion)
        companion_token = create_access_token({"sub": str(companion.id), "role": "companion"})
        await seed_companion_profile(user_id=companion.id)

        def as_patient():
            client.headers["Authorization"] = f"Bearer {patient_token}"

        def as_companion():
            client.headers["Authorization"] = f"Bearer {companion_token}"

        # 1. Create order as patient
        as_patient()
        order = await _create_order(client, hospital.id)
        order_id = order["id"]

        # 2. Pay
        resp = await client.post(f"/api/v1/orders/{order_id}/pay")
        assert resp.status_code == 200

        # 3. Companion accepts
        as_companion()
        resp = await client.post(f"/api/v1/orders/{order_id}/accept")
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

        # 4. Companion starts service → in_progress
        resp = await client.post(f"/api/v1/orders/{order_id}/start")
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_progress"

        # 5. Patient cancels during in_progress → triggers 50% auto-refund
        as_patient()
        resp = await client.post(f"/api/v1/orders/{order_id}/cancel")
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled_by_patient"

        # 6. Check wallet: refund should be 50% of 299 = 149.50
        expected_refund = round(299.0 * 0.5, 2)
        resp = await client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        refunds = [t for t in items if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == expected_refund
        assert refunds[0]["status"] == "success"

    async def test_refund_failure_idempotency(
        self, authenticated_client, seed_hospital
    ):
        """Duplicate refund on same order → only 1 refund entry, second call returns 400."""
        hospital = await seed_hospital()

        # 1. Create order & pay
        order = await _create_order(authenticated_client, hospital.id)
        order_id = order["id"]
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/pay")
        assert resp.status_code == 200

        # 2. Expire the order → auto-refund (first refund)
        async with test_session_factory() as session:
            await session.execute(
                update(Order)
                .where(Order.id == UUID(order_id))
                .values(expires_at=datetime.now(timezone.utc) - timedelta(hours=1))
            )
            await session.commit()

        resp = await authenticated_client.post("/api/v1/orders/check-expired")
        assert resp.status_code == 200
        assert order_id in resp.json()["cancelled_order_ids"]

        # 3. Attempt manual refund on the already-refunded order → should fail
        resp = await authenticated_client.post(f"/api/v1/orders/{order_id}/refund")
        assert resp.status_code == 400

        # 4. Wallet should have exactly 1 refund entry, not 2
        resp = await authenticated_client.get("/api/v1/wallet/transactions")
        assert resp.status_code == 200
        items = resp.json()["items"]
        refunds = [t for t in items if t["payment_type"] == "refund"]
        assert len(refunds) == 1
        assert refunds[0]["amount"] == 299.0
