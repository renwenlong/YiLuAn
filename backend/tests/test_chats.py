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



class TestListMessagesBeforeCursor:
    """Pull-up history pagination via ``?before_id=...&limit=...``."""

    @staticmethod
    def _ts(i: int):
        from datetime import datetime, timedelta, timezone

        return datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc) + timedelta(
            seconds=i
        )

    async def test_cursor_returns_older_page(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_chat_message,
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137201", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        msgs = []
        for i in range(10):
            m = await seed_chat_message(
                order.id, patient.id, content=f"m{i}", created_at=self._ts(i)
            )
            msgs.append(m)

        # Anchor on m7 → expect m4, m5, m6 (ascending)
        resp = await authenticated_client.get(
            f"/api/v1/chats/{order.id}/messages?before_id={msgs[7].id}&limit=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 10
        assert [i["content"] for i in data["items"]] == ["m4", "m5", "m6"]
        assert data["has_more"] is True
        assert data["next_before_id"] == str(msgs[4].id)

    async def test_cursor_signals_end_of_history(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_chat_message,
    ):
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137202", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        msgs = []
        for i in range(4):
            m = await seed_chat_message(
                order.id, patient.id, content=f"m{i}", created_at=self._ts(i)
            )
            msgs.append(m)

        # Anchor on m1: only m0 is older, limit 3 → has_more=False
        resp = await authenticated_client.get(
            f"/api/v1/chats/{order.id}/messages"
            f"?before_id={msgs[1].id}&limit=3"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert [i["content"] for i in data["items"]] == ["m0"]
        assert data["has_more"] is False
        assert data["next_before_id"] is None

    async def test_cursor_unknown_id_falls_back_to_tail(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_chat_message,
    ):
        import uuid as _uuid

        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137203", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        for i in range(3):
            await seed_chat_message(
                order.id, patient.id, content=f"m{i}", created_at=self._ts(i)
            )

        resp = await authenticated_client.get(
            f"/api/v1/chats/{order.id}/messages"
            f"?before_id={_uuid.uuid4()}&limit=2"
        )
        # Stale cursor → recover with tail of conversation rather than 404
        assert resp.status_code == 200
        data = resp.json()
        assert [i["content"] for i in data["items"]] == ["m1", "m2"]
        # 3 total, returned 2 → 1 older message remains → has_more
        assert data["has_more"] is True

    async def test_legacy_page_mode_still_returns_all(
        self,
        authenticated_client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_chat_message,
    ):
        """Passing ``limit`` alone (no ``before_id``) must NOT trigger cursor mode."""
        patient = authenticated_client._test_user
        companion = await seed_user(phone="13700137204", role=UserRole.companion)
        hospital = await seed_hospital()
        order = await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )
        for i in range(5):
            await seed_chat_message(
                order.id, patient.id, content=f"m{i}", created_at=self._ts(i)
            )

        resp = await authenticated_client.get(
            f"/api/v1/chats/{order.id}/messages?limit=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        # legacy path: page_size default = 50 → all 5 returned
        assert data["total"] == 5
        assert len(data["items"]) == 5
        assert data["has_more"] is False
