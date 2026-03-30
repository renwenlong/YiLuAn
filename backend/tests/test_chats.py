import pytest
from app.core.security import create_access_token
from app.models.order import OrderStatus
from app.models.user import UserRole


pytestmark = pytest.mark.asyncio


class TestSendMessage:
    async def test_send_message_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137100", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await authenticated_client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "你好，请问明天几点到？", "type": "text"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["content"] == "你好，请问明天几点到？"
        assert data["sender_id"] == str(patient.id)
        assert data["type"] == "text"
        assert data["is_read"] is False

    async def test_send_message_as_companion(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138100", role=UserRole.patient)
        companion = await seed_user(phone="13700137101", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        token = create_access_token({"sub": str(companion.id), "role": "companion"})
        client.headers["Authorization"] = f"Bearer {token}"

        resp = await client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "好的，明天9点到医院门口"},
        )
        assert resp.status_code == 201
        assert resp.json()["sender_id"] == str(companion.id)

    async def test_send_message_not_participant(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138101", role=UserRole.patient)
        companion = await seed_user(phone="13700137102", role=UserRole.companion)
        outsider = await seed_user(phone="13600136100", role=UserRole.patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        token = create_access_token({"sub": str(outsider.id), "role": "patient"})
        client.headers["Authorization"] = f"Bearer {token}"

        resp = await client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "我不属于这个订单"},
        )
        assert resp.status_code == 403

    async def test_send_message_order_not_found(self, authenticated_client):
        import uuid

        resp = await authenticated_client.post(
            f"/api/v1/chats/{uuid.uuid4()}/messages",
            json={"content": "订单不存在"},
        )
        assert resp.status_code == 404

    async def test_send_message_empty_content(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137103", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await authenticated_client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": ""},
        )
        assert resp.status_code == 422

    async def test_send_image_message(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137104", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await authenticated_client.post(
            f"/api/v1/chats/{order.id}/messages",
            json={"content": "https://example.com/image.jpg", "type": "image"},
        )
        assert resp.status_code == 201
        assert resp.json()["type"] == "image"


class TestListMessages:
    async def test_list_messages_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order, seed_chat_message
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137110", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        await seed_chat_message(order.id, patient.id, content="消息1")
        await seed_chat_message(order.id, companion.id, content="消息2")
        await seed_chat_message(order.id, patient.id, content="消息3")

        resp = await authenticated_client.get(f"/api/v1/chats/{order.id}/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        # Should be in chronological order
        assert data["items"][0]["content"] == "消息1"
        assert data["items"][2]["content"] == "消息3"

    async def test_list_messages_empty(
        self, authenticated_client, seed_user, seed_hospital, seed_order
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137111", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await authenticated_client.get(f"/api/v1/chats/{order.id}/messages")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    async def test_list_messages_not_participant(
        self, client, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13800138110", role=UserRole.patient)
        companion = await seed_user(phone="13700137112", role=UserRole.companion)
        outsider = await seed_user(phone="13600136110", role=UserRole.patient)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        token = create_access_token({"sub": str(outsider.id), "role": "patient"})
        client.headers["Authorization"] = f"Bearer {token}"

        resp = await client.get(f"/api/v1/chats/{order.id}/messages")
        assert resp.status_code == 403


class TestMarkRead:
    async def test_mark_read_success(
        self, authenticated_client, seed_user, seed_hospital, seed_order, seed_chat_message
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137120", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        # Companion sends messages
        await seed_chat_message(order.id, companion.id, content="消息A")
        await seed_chat_message(order.id, companion.id, content="消息B")

        # Patient marks as read
        resp = await authenticated_client.post(f"/api/v1/chats/{order.id}/read")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 2

    async def test_mark_read_own_messages_not_affected(
        self, authenticated_client, seed_user, seed_hospital, seed_order, seed_chat_message
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137121", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        # Patient sends own messages
        await seed_chat_message(order.id, patient.id, content="我的消息")

        # Mark read should not affect own messages
        resp = await authenticated_client.post(f"/api/v1/chats/{order.id}/read")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 0
