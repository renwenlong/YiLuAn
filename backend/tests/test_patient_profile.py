import pytest


@pytest.mark.asyncio
class TestPatientProfile:
    async def test_get_profile_auto_creates(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/users/me/patient-profile")
        assert resp.status_code == 200
        data = resp.json()
        assert data["user_id"] is not None
        assert data["emergency_contact"] is None

    async def test_update_profile_success(self, authenticated_client):
        resp = await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={
                "emergency_contact": "张三",
                "emergency_phone": "13900139001",
                "medical_notes": "过敏体质",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["emergency_contact"] == "张三"
        assert data["emergency_phone"] == "13900139001"
        assert data["medical_notes"] == "过敏体质"

    async def test_update_emergency_phone_invalid(self, authenticated_client):
        resp = await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={"emergency_phone": "abc123"},
        )
        assert resp.status_code == 422

    async def test_get_profile_no_auth(self, client):
        resp = await client.get("/api/v1/users/me/patient-profile")
        assert resp.status_code in (401, 403)

    async def test_update_profile_partial(self, authenticated_client):
        await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={"emergency_contact": "李四", "medical_notes": "糖尿病"},
        )
        resp = await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={"emergency_contact": "王五"},
        )
        data = resp.json()
        assert data["emergency_contact"] == "王五"
        assert data["medical_notes"] == "糖尿病"

    async def test_get_profile_after_update(self, authenticated_client):
        await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={"emergency_contact": "赵六"},
        )
        resp = await authenticated_client.get("/api/v1/users/me/patient-profile")
        assert resp.status_code == 200
        assert resp.json()["emergency_contact"] == "赵六"

    async def test_update_preferred_hospital(self, authenticated_client, seed_hospital):
        hospital = await seed_hospital(name="北京协和医院")
        resp = await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={"preferred_hospital_id": str(hospital.id)},
        )
        assert resp.status_code == 200
        assert resp.json()["preferred_hospital_id"] == str(hospital.id)

    async def test_update_empty_body(self, authenticated_client):
        resp = await authenticated_client.put(
            "/api/v1/users/me/patient-profile",
            json={},
        )
        assert resp.status_code == 200
