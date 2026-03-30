import uuid

import pytest
from app.models.notification import NotificationType
from app.models.user import UserRole


pytestmark = pytest.mark.asyncio


class TestListNotifications:
    async def test_list_notifications_success(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        await seed_notification(user.id, title="通知1", body="内容1")
        await seed_notification(user.id, title="通知2", body="内容2")

        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_notifications_empty(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        assert resp.json()["total"] == 0
        assert resp.json()["items"] == []

    async def test_list_notifications_pagination(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        for i in range(5):
            await seed_notification(user.id, title=f"通知{i}", body=f"内容{i}")

        resp = await authenticated_client.get(
            "/api/v1/notifications?page=1&page_size=2"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_list_notifications_no_auth(self, client):
        resp = await client.get("/api/v1/notifications")
        assert resp.status_code in (401, 403)

    async def test_list_notifications_only_own(
        self, authenticated_client, seed_user, seed_notification
    ):
        user = authenticated_client._test_user
        other = await seed_user(phone="13600136200", role=UserRole.patient)

        await seed_notification(user.id, title="我的通知", body="给我的")
        await seed_notification(other.id, title="别人的通知", body="给别人的")

        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.json()["total"] == 1


class TestUnreadCount:
    async def test_unread_count_success(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        await seed_notification(user.id, title="未读1", body="内容")
        await seed_notification(user.id, title="未读2", body="内容")

        resp = await authenticated_client.get("/api/v1/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 2

    async def test_unread_count_zero(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/notifications/unread-count")
        assert resp.status_code == 200
        assert resp.json()["count"] == 0


class TestMarkRead:
    async def test_mark_read_success(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        notification = await seed_notification(user.id, title="未读", body="标记已读")

        resp = await authenticated_client.post(
            f"/api/v1/notifications/{notification.id}/read"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify unread count decreased
        resp2 = await authenticated_client.get("/api/v1/notifications/unread-count")
        assert resp2.json()["count"] == 0

    async def test_mark_read_wrong_user(
        self, authenticated_client, seed_user, seed_notification
    ):
        other = await seed_user(phone="13600136210", role=UserRole.patient)
        notification = await seed_notification(other.id, title="别人的", body="不该标记")

        resp = await authenticated_client.post(
            f"/api/v1/notifications/{notification.id}/read"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False

    async def test_mark_read_not_found(self, authenticated_client):
        resp = await authenticated_client.post(
            f"/api/v1/notifications/{uuid.uuid4()}/read"
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is False


class TestMarkAllRead:
    async def test_mark_all_read_success(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        await seed_notification(user.id, title="未读1", body="内容")
        await seed_notification(user.id, title="未读2", body="内容")
        await seed_notification(user.id, title="未读3", body="内容")

        resp = await authenticated_client.post("/api/v1/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 3

        # Verify all read
        resp2 = await authenticated_client.get("/api/v1/notifications/unread-count")
        assert resp2.json()["count"] == 0

    async def test_mark_all_read_empty(self, authenticated_client):
        resp = await authenticated_client.post("/api/v1/notifications/read-all")
        assert resp.status_code == 200
        assert resp.json()["marked_read"] == 0

    async def test_notification_types(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        await seed_notification(
            user.id,
            type=NotificationType.order_status_changed,
            title="订单状态变更",
            body="您的订单已被接单",
            reference_id=str(uuid.uuid4()),
        )
        await seed_notification(
            user.id,
            type=NotificationType.new_message,
            title="新消息",
            body="陪诊师发来消息",
        )
        await seed_notification(
            user.id,
            type=NotificationType.review_received,
            title="收到评价",
            body="患者给了5星好评",
        )

        resp = await authenticated_client.get("/api/v1/notifications")
        data = resp.json()
        assert data["total"] == 3
        types = {item["type"] for item in data["items"]}
        assert "order_status_changed" in types
        assert "new_message" in types
        assert "review_received" in types
