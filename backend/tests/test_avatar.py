import io

import pytest


@pytest.mark.asyncio
class TestAvatarUpload:
    async def test_upload_avatar_success(self, authenticated_client):
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        resp = await authenticated_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("test.png", io.BytesIO(image_data), "image/png")},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "avatar_url" in data
        assert data["avatar_url"].endswith(".png")

    async def test_upload_avatar_invalid_type(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("test.gif", io.BytesIO(b"GIF89a"), "image/gif")},
        )
        assert resp.status_code == 400

    async def test_upload_avatar_too_large(self, authenticated_client):
        large_data = b"\x00" * (6 * 1024 * 1024)
        resp = await authenticated_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("big.png", io.BytesIO(large_data), "image/png")},
        )
        assert resp.status_code == 400

    async def test_upload_avatar_no_auth(self, client):
        resp = await client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("test.png", io.BytesIO(b"data"), "image/png")},
        )
        assert resp.status_code in (401, 403)

    async def test_upload_avatar_updates_user(self, authenticated_client):
        image_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        await authenticated_client.post(
            "/api/v1/users/me/avatar",
            files={"file": ("test.png", io.BytesIO(image_data), "image/png")},
        )
        resp = await authenticated_client.get("/api/v1/users/me")
        assert resp.status_code == 200
        assert resp.json()["avatar_url"] is not None
