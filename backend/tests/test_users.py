import pytest

from app.core.security import create_access_token


# ===========================================================================
# GET /api/v1/users/me
# ===========================================================================
class TestGetMe:
    async def test_get_me_success(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/users/me")
        assert response.status_code == 200
        data = response.json()
        assert data["phone"] == "13800138000"
        assert data["role"] == "patient"

    async def test_get_me_no_token(self, client):
        response = await client.get("/api/v1/users/me")
        assert response.status_code == 403

    async def test_get_me_invalid_token(self, client):
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer invalid-token"},
        )
        assert response.status_code == 401

    async def test_get_me_response_schema(self, authenticated_client):
        response = await authenticated_client.get("/api/v1/users/me")
        data = response.json()
        required_fields = {"id", "phone", "role", "display_name", "avatar_url", "created_at"}
        assert required_fields.issubset(set(data.keys()))


# ===========================================================================
# PUT /api/v1/users/me
# ===========================================================================
class TestUpdateMe:
    async def test_update_role_success(self, no_role_client):
        response = await no_role_client.put(
            "/api/v1/users/me", json={"role": "patient"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["role"] == "patient"

    async def test_update_display_name(self, authenticated_client):
        response = await authenticated_client.put(
            "/api/v1/users/me", json={"display_name": "张三"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["display_name"] == "张三"

    async def test_update_role_already_set(self, authenticated_client):
        # User already has role=patient, trying to change to companion
        response = await authenticated_client.put(
            "/api/v1/users/me", json={"role": "companion"}
        )
        assert response.status_code == 400
        assert "cannot be changed" in response.json()["detail"].lower()

    async def test_update_invalid_role(self, no_role_client):
        response = await no_role_client.put(
            "/api/v1/users/me", json={"role": "admin"}
        )
        assert response.status_code == 422

    async def test_update_no_auth(self, client):
        response = await client.put(
            "/api/v1/users/me", json={"display_name": "test"}
        )
        assert response.status_code == 403
