import pytest
from app.core.security import create_access_token
from app.models.user import UserRole


pytestmark = pytest.mark.asyncio


class TestRegisterDeviceToken:
    async def test_register_device_success(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/notifications/device-token",
            json={"token": "apns_test_token_001", "device_type": "ios"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["token"] == "apns_test_token_001"
        assert data["device_type"] == "ios"
        assert "id" in data
        assert "created_at" in data

    async def test_register_device_duplicate_is_idempotent(
        self, authenticated_client
    ):
        body = {"token": "apns_test_token_002", "device_type": "ios"}
        resp1 = await authenticated_client.post(
            "/api/v1/notifications/device-token", json=body,
        )
        assert resp1.status_code == 200
        id1 = resp1.json()["id"]

        resp2 = await authenticated_client.post(
            "/api/v1/notifications/device-token", json=body,
        )
        assert resp2.status_code == 200
        assert resp2.json()["id"] == id1

    async def test_register_device_no_auth(self, client):
        resp = await client.post(
            "/api/v1/notifications/device-token",
            json={"token": "apns_test_token_003", "device_type": "ios"},
        )
        assert resp.status_code in (401, 403)

    async def test_register_device_invalid_type(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/notifications/device-token",
            json={"token": "apns_test_token_004", "device_type": "blackberry"},
        )
        assert resp.status_code == 422

    async def test_register_wechat_device(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/notifications/device-token",
            json={"token": "wx_push_token_001", "device_type": "wechat"},
        )
        assert resp.status_code == 200
        assert resp.json()["device_type"] == "wechat"


class TestDeleteDeviceToken:
    async def test_delete_device_success(self, authenticated_client):
        # Register first
        await authenticated_client.post(
            "/api/v1/notifications/device-token",
            json={"token": "apns_delete_token_001", "device_type": "ios"},
        )

        # Delete
        resp = await authenticated_client.request(
            "DELETE",
            "/api/v1/notifications/device-token",
            json={"token": "apns_delete_token_001"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    async def test_delete_device_not_found_silent(self, authenticated_client):
        resp = await authenticated_client.request(
            "DELETE",
            "/api/v1/notifications/device-token",
            json={"token": "nonexistent_token_xyz"},
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
