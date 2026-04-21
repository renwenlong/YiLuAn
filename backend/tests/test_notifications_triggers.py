import uuid

import pytest
from app.core.security import create_access_token
from app.models.notification import NotificationType
from app.models.order import OrderStatus
from app.models.user import UserRole


pytestmark = pytest.mark.asyncio


class TestOrderNotificationTriggers:
    async def test_accept_order_creates_notification(
        self, companion_client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138100", role=UserRole.patient)
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id, status=OrderStatus.created)

        resp = await companion_client.post(f"/api/v1/orders/{order.id}/accept")
        assert resp.status_code == 200

        # Check patient notifications
        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await companion_client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 1
        notif = items[0]
        assert notif["type"] == NotificationType.order_status_changed.value
        assert str(order.id) in notif["reference_id"]

    async def test_start_order_creates_notification(
        self, client, seed_user, seed_hospital, seed_order, seed_companion_profile, seed_payment
    ):
        patient = await seed_user(phone="13800138101", role=UserRole.patient)
        companion = await seed_user(phone="13700137101", role=UserRole.companion)
        await seed_companion_profile(user_id=companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        await seed_payment(order.id, patient.id)

        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.post(
            f"/api/v1/orders/{order.id}/start",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200

        # Check patient notifications
        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.order_status_changed.value for n in items
        )

    async def test_complete_order_creates_notification(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138102", role=UserRole.patient)
        companion = await seed_user(phone="13700137102", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.in_progress,
        )

        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.post(
            f"/api/v1/orders/{order.id}/complete",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200

        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.order_status_changed.value for n in items
        )

    async def test_cancel_order_notifies_companion(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138103", role=UserRole.patient)
        companion = await seed_user(phone="13700137103", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.post(
            f"/api/v1/orders/{order.id}/cancel",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200

        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.order_status_changed.value for n in items
        )


    async def test_request_start_creates_notification(
        self, client, seed_user, seed_hospital, seed_order
    ):
        """Companion request-start sends start_service_request notification to patient."""
        patient = await seed_user(phone="13800138104", role=UserRole.patient)
        companion = await seed_user(phone="13700137104", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.post(
            f"/api/v1/orders/{order.id}/request-start",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200

        # Patient should have start_service_request notification
        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.start_service_request.value for n in items
        )

    async def test_confirm_start_notifies_companion(
        self, client, seed_user, seed_hospital, seed_order, seed_payment
    ):
        """Patient confirm-start sends order_status_changed notification to companion."""
        patient = await seed_user(phone="13800138105", role=UserRole.patient)
        companion = await seed_user(phone="13700137105", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        await seed_payment(order.id, patient.id)

        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.post(
            f"/api/v1/orders/{order.id}/confirm-start",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 200

        # Companion should have order_status_changed notification
        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.order_status_changed.value for n in items
        )


class TestReviewNotificationTrigger:
    async def test_submit_review_notifies_companion(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_companion_profile,
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137110", role=UserRole.companion)
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        resp = await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 5, "content": "非常好的陪诊服务！"},
        )
        assert resp.status_code == 201

        # Companion should have a review_received notification
        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await authenticated_client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.review_received.value for n in items
        )

    async def test_review_notification_has_correct_reference(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_companion_profile,
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137111", role=UserRole.companion)
        await seed_companion_profile(companion.id)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
        )

        await authenticated_client.post(
            f"/api/v1/orders/{order.id}/review",
            json={"rating": 3, "content": "服务不错可以更好"},
        )

        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await authenticated_client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        items = resp.json()["items"]
        review_notif = next(
            n for n in items if n["type"] == NotificationType.review_received.value
        )
        assert review_notif["reference_id"] == str(order.id)


class TestChatNotificationTrigger:
    async def test_send_message_notifies_recipient(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138120", role=UserRole.patient)
        companion = await seed_user(phone="13700137120", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        # Patient sends message
        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        resp = await client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "你好，请问几点到？", "type": "text"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        assert resp.status_code == 201

        # Companion should receive new_message notification
        companion_token = create_access_token(
            {"sub": str(companion.id), "role": "companion"}
        )
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {companion_token}"},
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert any(
            n["type"] == NotificationType.new_message.value for n in items
        )

    async def test_no_self_notification(
        self, client, seed_user, seed_hospital, seed_order
    ):
        """Sender should NOT get a notification for their own message."""
        patient = await seed_user(phone="13800138121", role=UserRole.patient)
        companion = await seed_user(phone="13700137121", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        patient_token = create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        )
        await client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "我发的消息", "type": "text"},
            headers={"Authorization": f"Bearer {patient_token}"},
        )

        # Patient should NOT have a new_message notification
        resp = await client.get(
            "/api/v1/notifications",
            headers={"Authorization": f"Bearer {patient_token}"},
        )
        items = resp.json()["items"]
        assert not any(
            n["type"] == NotificationType.new_message.value for n in items
        )
