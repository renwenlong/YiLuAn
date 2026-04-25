"""[F-03] Emergency call & contacts API tests."""
import pytest


@pytest.mark.asyncio
class TestEmergencyContacts:
    async def test_list_empty(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/emergency/contacts")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create_contact(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "妈妈", "phone": "13900139000", "relationship": "母亲"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "妈妈"
        assert data["phone"] == "13900139000"
        assert data["relationship"] == "母亲"

    async def test_create_invalid_phone(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "X", "phone": "abc", "relationship": "朋友"},
        )
        assert resp.status_code == 422

    async def test_create_limit_three(self, authenticated_client):
        for i in range(3):
            resp = await authenticated_client.post(
                "/api/v1/emergency/contacts",
                json={
                    "name": f"联系人{i}",
                    "phone": f"1390013900{i}",
                    "relationship": "朋友",
                },
            )
            assert resp.status_code == 201
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "第四", "phone": "13900139009", "relationship": "朋友"},
        )
        assert resp.status_code == 409

    async def test_update_contact(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "A", "phone": "13900139000", "relationship": "朋友"},
        )
        cid = resp.json()["id"]
        resp = await authenticated_client.put(
            f"/api/v1/emergency/contacts/{cid}",
            json={"name": "B"},
        )
        assert resp.status_code == 200
        assert resp.json()["name"] == "B"
        assert resp.json()["phone"] == "13900139000"

    async def test_delete_contact(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "A", "phone": "13900139000", "relationship": "朋友"},
        )
        cid = resp.json()["id"]
        resp = await authenticated_client.delete(f"/api/v1/emergency/contacts/{cid}")
        assert resp.status_code == 204
        resp = await authenticated_client.get("/api/v1/emergency/contacts")
        assert resp.json() == []

    async def test_other_user_cannot_modify(self, authenticated_client, client, seed_user):
        from app.core.security import create_access_token
        from app.models.user import UserRole

        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "A", "phone": "13900139000", "relationship": "朋友"},
        )
        cid = resp.json()["id"]
        # second user
        other = await seed_user(phone="13700137777", role=UserRole.patient)
        token = create_access_token({"sub": str(other.id), "role": "patient"})
        client.headers["Authorization"] = f"Bearer {token}"
        resp = await client.delete(f"/api/v1/emergency/contacts/{cid}")
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestEmergencyEvents:
    async def test_hotline_endpoint(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/emergency/hotline")
        assert resp.status_code == 200
        assert "hotline" in resp.json()

    async def test_trigger_with_contact(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/contacts",
            json={"name": "A", "phone": "13900139000", "relationship": "朋友"},
        )
        cid = resp.json()["id"]
        resp = await authenticated_client.post(
            "/api/v1/emergency/events",
            json={"contact_id": cid, "location": "急诊楼一层"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["phone_to_call"] == "13900139000"
        assert body["event"]["contact_type"] == "contact"
        assert body["event"]["location"] == "急诊楼一层"

    async def test_trigger_with_hotline(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/events",
            json={"hotline": True},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["event"]["contact_type"] == "hotline"
        assert body["phone_to_call"]  # not empty

    async def test_trigger_requires_target(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/emergency/events",
            json={},
        )
        assert resp.status_code == 400

    async def test_trigger_with_order(
        self, authenticated_client, seed_hospital, seed_order
    ):
        hospital = await seed_hospital()
        order = await seed_order(
            patient_id=authenticated_client._test_user.id,
            hospital_id=hospital.id,
        )
        resp = await authenticated_client.post(
            "/api/v1/emergency/events",
            json={"hotline": True, "order_id": str(order.id)},
        )
        assert resp.status_code == 201
        assert resp.json()["event"]["order_id"] == str(order.id)

    async def test_list_events(self, authenticated_client):
        await authenticated_client.post(
            "/api/v1/emergency/events", json={"hotline": True}
        )
        await authenticated_client.post(
            "/api/v1/emergency/events", json={"hotline": True}
        )
        resp = await authenticated_client.get("/api/v1/emergency/events")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    async def test_unauth_blocked(self, client):
        resp = await client.get("/api/v1/emergency/contacts")
        assert resp.status_code in (401, 403)
        resp = await client.post("/api/v1/emergency/events", json={"hotline": True})
        assert resp.status_code in (401, 403)
