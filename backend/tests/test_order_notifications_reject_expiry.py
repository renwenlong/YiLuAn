"""Tests for order notification, reject, and expiry features."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.order import OrderStatus, ServiceType


@pytest.mark.asyncio
class TestNewOrderNotification:
    """Tests for new order notification on payment."""

    async def test_pay_order_notifies_assigned_companion(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_companion_profile,
    ):
        hospital = await seed_hospital()
        companion_user = companion_client._test_user
        await seed_companion_profile(companion_user.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=companion_user.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        # Pay the order
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200

        # Check companion received a new_order notification
        resp2 = await companion_client.get("/api/v1/notifications")
        assert resp2.status_code == 200
        items = resp2.json()["items"]
        new_order_notifs = [n for n in items if n["type"] == "new_order"]
        assert len(new_order_notifs) >= 1
        assert "新订单来啦" in new_order_notifs[0]["title"]

    async def test_pay_order_broadcast_when_no_companion(
        self, authenticated_client, seed_hospital, seed_order,
    ):
        hospital = await seed_hospital()
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        # Pay - no companion assigned, broadcast goes to verified companions (none in test = ok)
        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/pay")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestRejectOrder:
    """Tests for companion rejecting an order."""

    async def test_reject_order_success(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_companion_profile,
    ):
        hospital = await seed_hospital()
        companion_user = companion_client._test_user
        await seed_companion_profile(companion_user.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=companion_user.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        resp = await companion_client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected_by_companion"

    async def test_reject_order_with_refund(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_payment, seed_companion_profile,
    ):
        hospital = await seed_hospital()
        companion_user = companion_client._test_user
        await seed_companion_profile(companion_user.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=companion_user.id,
            patient_name="测试患者", hospital_name="测试医院",
        )
        await seed_payment(order.id, patient_user.id, amount=299.0)

        resp = await companion_client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected_by_companion"

    async def test_reject_broadcast_order_fails(
        self, client, seed_user, seed_hospital, seed_order,
    ):
        """Broadcast orders (no companion_id) cannot be rejected."""
        from app.core.security import create_access_token
        from app.models.user import UserRole

        hospital = await seed_hospital()
        patient = await seed_user(phone="13800138077", role=UserRole.patient)
        companion = await seed_user(phone="13700137077", role=UserRole.companion)
        order = await seed_order(
            patient.id, hospital.id, companion_id=None,
            patient_name="测试患者", hospital_name="测试医院",
        )

        token = create_access_token({"sub": str(companion.id), "role": "companion"})
        client.headers["Authorization"] = f"Bearer {token}"
        resp = await client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 400

    async def test_reject_order_wrong_companion(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_user, seed_companion_profile,
    ):
        hospital = await seed_hospital()
        other_companion = await seed_user(phone="13700137999", role="companion")
        await seed_companion_profile(other_companion.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=other_companion.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        resp = await companion_client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 403

    async def test_reject_non_created_order_fails(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_companion_profile,
    ):
        hospital = await seed_hospital()
        companion_user = companion_client._test_user
        await seed_companion_profile(companion_user.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=companion_user.id,
            status=OrderStatus.accepted,
            patient_name="测试患者", hospital_name="测试医院",
        )

        resp = await companion_client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 400

    async def test_patient_cannot_reject(
        self, authenticated_client, seed_hospital, seed_order,
    ):
        hospital = await seed_hospital()
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        resp = await authenticated_client.post(f"/api/v1/orders/{order.id}/reject")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestOrderExpiry:
    """Tests for order expiry check."""

    async def test_check_expired_cancels_orders(
        self, client, seed_user, seed_hospital, seed_order,
    ):
        from tests.conftest import test_session_factory

        patient = await seed_user(phone="13800138099", role="patient")
        hospital = await seed_hospital()

        # Create an order with expires_at in the past
        async with test_session_factory() as session:
            from app.models.order import Order
            order = Order(
                order_number=f"YLAEXPIRED{uuid.uuid4().hex[:6].upper()}",
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.created,
                appointment_date="2026-04-15",
                appointment_time="09:00",
                price=299.0,
                patient_name="测试患者",
                hospital_name="测试医院",
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            order_id = order.id

        resp = await client.post("/api/v1/orders/check-expired")
        assert resp.status_code == 200
        data = resp.json()
        assert data["cancelled_count"] >= 1
        assert str(order_id) in data["cancelled_order_ids"]

    async def test_check_expired_ignores_non_expired(
        self, client, seed_user, seed_hospital, seed_order,
    ):
        patient = await seed_user(phone="13800138098", role="patient")
        hospital = await seed_hospital()

        # Create an order that has NOT expired yet
        order = await seed_order(
            patient.id, hospital.id,
            patient_name="测试患者", hospital_name="测试医院",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=3),
        )

        resp = await client.post("/api/v1/orders/check-expired")
        assert resp.status_code == 200
        assert resp.json()["cancelled_count"] == 0


@pytest.mark.asyncio
class TestOrderExpiresAtField:
    """Test that expires_at is set on order creation."""

    async def test_create_order_has_expires_at(
        self, authenticated_client, seed_hospital,
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["expires_at"] is not None


@pytest.mark.asyncio
class TestNotificationMessages:
    """Test notification message content."""

    async def test_reject_notification_sent_to_patient(
        self, authenticated_client, companion_client, seed_hospital, seed_order,
        seed_companion_profile,
    ):
        hospital = await seed_hospital()
        companion_user = companion_client._test_user
        await seed_companion_profile(companion_user.id)
        patient_user = authenticated_client._test_user
        order = await seed_order(
            patient_user.id, hospital.id, companion_id=companion_user.id,
            patient_name="测试患者", hospital_name="测试医院",
        )

        await companion_client.post(f"/api/v1/orders/{order.id}/reject")

        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        assert "重新安排" in items[0]["title"]
