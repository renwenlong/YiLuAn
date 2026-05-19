"""F-05: tests for family-member CRUD + 代他人下单 order create path."""

import uuid

import pytest


@pytest.mark.asyncio
class TestFamilyMemberCrud:
    async def test_list_empty_for_new_user(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/users/me/family-members")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {"items": [], "total": 0}

    async def test_create_then_list(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/users/me/family-members",
            json={
                "name": "妈妈",
                "relation": "parent",
                "phone": "13900001111",
                "gender": "female",
                "age": 65,
                "medical_notes": "高血压，青霉素过敏",
            },
        )
        assert resp.status_code == 201, resp.text
        created = resp.json()
        assert created["name"] == "妈妈"
        assert created["relation"] == "parent"
        assert created["phone"] == "13900001111"
        assert created["gender"] == "female"
        assert created["age"] == 65

        listing = await authenticated_client.get(
            "/api/v1/users/me/family-members"
        )
        assert listing.status_code == 200
        body = listing.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == created["id"]

    async def test_create_minimal_defaults_to_other_unknown(
        self, authenticated_client
    ):
        resp = await authenticated_client.post(
            "/api/v1/users/me/family-members",
            json={"name": "邻居老李"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["relation"] == "other"
        assert body["gender"] == "unknown"
        assert body["phone"] is None

    async def test_create_rejects_invalid_phone(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/users/me/family-members",
            json={"name": "妈妈", "phone": "123"},
        )
        assert resp.status_code == 422

    async def test_create_rejects_invalid_relation(self, authenticated_client):
        resp = await authenticated_client.post(
            "/api/v1/users/me/family-members",
            json={"name": "妈妈", "relation": "boss"},
        )
        assert resp.status_code == 422

    async def test_update_patch_partial(self, authenticated_client):
        created = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={"name": "妈妈", "relation": "parent"},
            )
        ).json()
        resp = await authenticated_client.patch(
            f"/api/v1/users/me/family-members/{created['id']}",
            json={"age": 70, "medical_notes": "新增冠心病"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["age"] == 70
        assert body["medical_notes"] == "新增冠心病"
        assert body["name"] == "妈妈"  # unchanged

    async def test_delete_is_soft_and_hidden_from_list(
        self, authenticated_client
    ):
        created = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={"name": "妈妈"},
            )
        ).json()
        resp = await authenticated_client.delete(
            f"/api/v1/users/me/family-members/{created['id']}"
        )
        assert resp.status_code == 204
        listing = (
            await authenticated_client.get("/api/v1/users/me/family-members")
        ).json()
        assert listing == {"items": [], "total": 0}

        # second delete → 404 (already gone from active scope)
        resp2 = await authenticated_client.delete(
            f"/api/v1/users/me/family-members/{created['id']}"
        )
        assert resp2.status_code == 404

    async def test_other_user_cannot_see_or_mutate(
        self, authenticated_client, seed_user
    ):
        from app.core.security import create_access_token
        from app.models.user import UserRole

        # owner (already authenticated) creates a member
        created = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={"name": "妈妈"},
            )
        ).json()

        # swap to a second user on the same client
        owner_auth = authenticated_client.headers.get("Authorization")
        other = await seed_user(phone="13700000999", role=UserRole.patient)
        other_token = create_access_token(
            {"sub": str(other.id), "role": "patient"}
        )
        authenticated_client.headers["Authorization"] = f"Bearer {other_token}"

        # second user lists → not visible
        other_list = (
            await authenticated_client.get("/api/v1/users/me/family-members")
        ).json()
        assert all(item["id"] != created["id"] for item in other_list["items"])

        # second user can't update / delete (owner-scoped 404)
        upd = await authenticated_client.patch(
            f"/api/v1/users/me/family-members/{created['id']}",
            json={"name": "hack"},
        )
        assert upd.status_code == 404
        rm = await authenticated_client.delete(
            f"/api/v1/users/me/family-members/{created['id']}"
        )
        assert rm.status_code == 404

        # restore the owner token for any teardown that may peek
        authenticated_client.headers["Authorization"] = owner_auth


@pytest.mark.asyncio
class TestCreateOrderForFamilyMember:
    async def test_create_order_for_self_keeps_family_member_null(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-01",
                "appointment_time": "09:00",
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body.get("family_member") is None

    async def test_create_order_with_family_member_id_embeds_snapshot(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        fm = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={
                    "name": "爷爷",
                    "relation": "grandparent",
                    "phone": "13511112222",
                },
            )
        ).json()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "half_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-02",
                "appointment_time": "10:30",
                "family_member_id": fm["id"],
            },
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["family_member"] is not None
        snap = body["family_member"]
        assert snap["id"] == fm["id"]
        assert snap["name"] == "爷爷"
        assert snap["relation"] == "grandparent"
        assert snap["phone"] == "13511112222"

    async def test_create_order_with_unknown_family_member_404(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "errand",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-03",
                "appointment_time": "11:00",
                "family_member_id": str(uuid.uuid4()),
            },
        )
        assert resp.status_code == 404

    async def test_create_order_rejects_other_users_family_member(
        self, authenticated_client, seed_hospital, seed_user
    ):
        from app.core.security import create_access_token
        from app.models.user import UserRole

        hospital = await seed_hospital()
        # seed an "other" user and create a family member as them by
        # swapping the token in-flight (single shared httpx client).
        owner_auth = authenticated_client.headers.get("Authorization")
        other = await seed_user(phone="13700000888", role=UserRole.patient)
        other_token = create_access_token(
            {"sub": str(other.id), "role": "patient"}
        )
        authenticated_client.headers["Authorization"] = f"Bearer {other_token}"
        fm_other = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={"name": "陌生人"},
            )
        ).json()
        # switch back to primary user
        authenticated_client.headers["Authorization"] = owner_auth

        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-06-04",
                "appointment_time": "12:00",
                "family_member_id": fm_other["id"],
            },
        )
        assert resp.status_code == 404

    async def test_snapshot_survives_family_member_soft_delete(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()
        fm = (
            await authenticated_client.post(
                "/api/v1/users/me/family-members",
                json={"name": "奶奶", "relation": "grandparent"},
            )
        ).json()
        created = (
            await authenticated_client.post(
                "/api/v1/orders",
                json={
                    "service_type": "full_accompany",
                    "hospital_id": str(hospital.id),
                    "appointment_date": "2026-06-05",
                    "appointment_time": "13:00",
                    "family_member_id": fm["id"],
                },
            )
        ).json()
        # soft-delete the family member
        rm = await authenticated_client.delete(
            f"/api/v1/users/me/family-members/{fm['id']}"
        )
        assert rm.status_code == 204
        # historical order still resolves with full snapshot
        again = await authenticated_client.get(
            f"/api/v1/orders/{created['id']}"
        )
        assert again.status_code == 200, again.text
        body = again.json()
        assert body["family_member"]["name"] == "奶奶"
        assert body["family_member"]["relation"] == "grandparent"
