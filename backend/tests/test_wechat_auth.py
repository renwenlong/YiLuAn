from unittest.mock import AsyncMock, patch

import pytest

from app.core.security import create_access_token, decode_token
from app.exceptions import BadRequestException


MOCK_CODE2SESSION = {
    "openid": "mock_openid_12345",
    "session_key": "mock_session_key",
    "unionid": None,
}


# ===========================================================================
# POST /api/v1/auth/wechat-login
# ===========================================================================
class TestWeChatLogin:
    async def test_wechat_login_new_user(self, client):
        with patch(
            "app.services.auth.WeChatAPIClient.code2session",
            new_callable=AsyncMock,
            return_value=MOCK_CODE2SESSION,
        ):
            response = await client.post(
                "/api/v1/auth/wechat-login", json={"code": "valid_wx_code"}
            )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["phone"] is None
        assert data["user"]["role"] is None
        assert "id" in data["user"]

    async def test_wechat_login_existing_user(self, client, seed_wechat_user):
        user = await seed_wechat_user(openid="mock_openid_12345")
        with patch(
            "app.services.auth.WeChatAPIClient.code2session",
            new_callable=AsyncMock,
            return_value=MOCK_CODE2SESSION,
        ):
            response = await client.post(
                "/api/v1/auth/wechat-login", json={"code": "valid_wx_code"}
            )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == str(user.id)

    async def test_wechat_login_invalid_code(self, client):
        with patch(
            "app.services.auth.WeChatAPIClient.code2session",
            new_callable=AsyncMock,
            side_effect=BadRequestException("WeChat login failed: invalid code"),
        ):
            response = await client.post(
                "/api/v1/auth/wechat-login", json={"code": "invalid_code"}
            )
        assert response.status_code == 400
        assert "WeChat login failed" in response.json()["detail"]

    async def test_wechat_login_disabled_user(self, client, seed_wechat_user):
        await seed_wechat_user(openid="mock_openid_12345", is_active=False)
        with patch(
            "app.services.auth.WeChatAPIClient.code2session",
            new_callable=AsyncMock,
            return_value=MOCK_CODE2SESSION,
        ):
            response = await client.post(
                "/api/v1/auth/wechat-login", json={"code": "valid_wx_code"}
            )
        assert response.status_code == 401
        assert "disabled" in response.json()["detail"].lower()

    async def test_wechat_login_dev_bypass(self, client):
        response = await client.post(
            "/api/v1/auth/wechat-login", json={"code": "dev_test_code"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["phone"] is None

    async def test_wechat_login_returns_valid_tokens(self, client):
        with patch(
            "app.services.auth.WeChatAPIClient.code2session",
            new_callable=AsyncMock,
            return_value=MOCK_CODE2SESSION,
        ):
            response = await client.post(
                "/api/v1/auth/wechat-login", json={"code": "valid_wx_code"}
            )
        data = response.json()
        access_payload = decode_token(data["access_token"])
        assert access_payload is not None
        assert access_payload["type"] == "access"
        assert "sub" in access_payload

        refresh_payload = decode_token(data["refresh_token"])
        assert refresh_payload is not None
        assert refresh_payload["type"] == "refresh"
        assert refresh_payload["sub"] == access_payload["sub"]


# ===========================================================================
# POST /api/v1/auth/bind-phone
# ===========================================================================
class TestBindPhone:
    async def test_bind_phone_success(self, wechat_client, fake_redis):
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await wechat_client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "13800138000"

    async def test_bind_phone_already_bound(self, client, seed_user, fake_redis):
        user = await seed_user(phone="13800138000")
        token = create_access_token({"sub": str(user.id), "role": None})
        client.headers["Authorization"] = f"Bearer {token}"
        await fake_redis.set("otp:13900139000", "123456", ex=300)
        response = await client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13900139000", "code": "123456"},
        )
        assert response.status_code == 400
        assert "already has a phone" in response.json()["detail"].lower()

    async def test_bind_phone_phone_taken(self, wechat_client, fake_redis, seed_user):
        await seed_user(phone="13800138000")
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await wechat_client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()

    async def test_bind_phone_invalid_otp(self, wechat_client, fake_redis):
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await wechat_client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13800138000", "code": "999999"},
        )
        assert response.status_code == 400
        assert "Invalid OTP" in response.json()["detail"]

    async def test_bind_phone_expired_otp(self, wechat_client):
        response = await wechat_client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    async def test_bind_phone_no_auth(self, client):
        response = await client.post(
            "/api/v1/auth/bind-phone",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 403
