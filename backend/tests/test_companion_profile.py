import pytest

from app.models.user import UserRole


@pytest.mark.asyncio
class TestCompanionProfile:
    async def test_apply_companion_success(self, no_role_client):
        resp = await no_role_client.post(
            "/api/v1/companions/apply",
            json={
                "real_name": "陈医生",
                "service_area": "朝阳区",
                "service_types": "全程陪诊",
                "bio": "资深陪诊",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["real_name"] == "陈医生"
        assert data["service_area"] == "朝阳区"
        assert data["verification_status"] == "pending"

    async def test_apply_companion_duplicate(self, no_role_client):
        await no_role_client.post(
            "/api/v1/companions/apply",
            json={"real_name": "陈医生", "service_types": "全程陪诊"},
        )
        resp = await no_role_client.post(
            "/api/v1/companions/apply",
            json={"real_name": "陈医生", "service_types": "全程陪诊"},
        )
        assert resp.status_code == 409

    async def test_apply_companion_missing_name(self, no_role_client):
        resp = await no_role_client.post(
            "/api/v1/companions/apply",
            json={"bio": "some bio"},
        )
        assert resp.status_code == 422

    async def test_apply_companion_name_too_short(self, no_role_client):
        resp = await no_role_client.post(
            "/api/v1/companions/apply",
            json={"real_name": "陈"},
        )
        assert resp.status_code == 422

    async def test_list_companions_empty(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/companions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_companions_with_data(
        self, authenticated_client, seed_user, seed_companion_profile
    ):
        user = await seed_user(phone="13600136000", role=UserRole.companion)
        await seed_companion_profile(user_id=user.id, service_area="海淀区")
        resp = await authenticated_client.get("/api/v1/companions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["service_area"] == "海淀区"

    async def test_list_companions_filter_area(
        self, authenticated_client, seed_user, seed_companion_profile
    ):
        u1 = await seed_user(phone="13600136001", role=UserRole.companion)
        u2 = await seed_user(phone="13600136002", role=UserRole.companion)
        await seed_companion_profile(user_id=u1.id, service_area="海淀区")
        await seed_companion_profile(
            user_id=u2.id, real_name="另一位", service_area="朝阳区"
        )
        resp = await authenticated_client.get("/api/v1/companions?area=海淀")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["service_area"] == "海淀区"

    async def test_get_companion_detail(
        self, authenticated_client, seed_user, seed_companion_profile
    ):
        user = await seed_user(phone="13600136003", role=UserRole.companion)
        profile = await seed_companion_profile(user_id=user.id)
        resp = await authenticated_client.get(f"/api/v1/companions/{profile.id}")
        assert resp.status_code == 200
        assert resp.json()["real_name"] == "测试陪诊师"

    async def test_get_companion_not_found(self, authenticated_client):
        import uuid

        resp = await authenticated_client.get(
            f"/api/v1/companions/{uuid.uuid4()}"
        )
        assert resp.status_code == 404

    async def test_update_companion_profile(
        self, companion_client, seed_companion_profile
    ):
        user = companion_client._test_user
        await seed_companion_profile(user_id=user.id)
        resp = await companion_client.put(
            "/api/v1/companions/me",
            json={"bio": "更新后的简介", "service_area": "西城区"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bio"] == "更新后的简介"
        assert data["service_area"] == "西城区"

    async def test_update_companion_no_auth(self, client):
        resp = await client.put(
            "/api/v1/companions/me",
            json={"bio": "test"},
        )
        assert resp.status_code in (401, 403)
