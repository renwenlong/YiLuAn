import pytest

from app.models.order import OrderStatus, ServiceType
from app.models.user import UserRole


class TestCompanionStats:
    async def test_get_stats_empty(
        self, companion_client, seed_companion_profile
    ):
        user = companion_client._test_user
        await seed_companion_profile(user.id)

        resp = await companion_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["today_orders"] == 0
        assert data["total_orders"] == 0
        assert data["avg_rating"] == 0.0
        assert data["total_earnings"] == 0.0

    async def test_get_stats_with_orders(
        self,
        companion_client,
        seed_companion_profile,
        seed_hospital,
        seed_order,
        seed_user,
    ):
        companion = companion_client._test_user
        await seed_companion_profile(companion.id)
        patient = await seed_user(phone="13600136000", role=UserRole.patient)
        hospital = await seed_hospital()

        # Create a completed order assigned to this companion
        await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.completed,
            price=299.0,
        )
        # Create another completed order
        await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.reviewed,
            price=199.0,
        )

        resp = await companion_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["today_orders"] == 2
        assert data["total_earnings"] == 498.0

    async def test_get_stats_no_auth(self, client):
        resp = await client.get("/api/v1/companions/me/stats")
        assert resp.status_code in (401, 403)

    async def test_get_stats_patient_forbidden(self, authenticated_client):
        resp = await authenticated_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 403

    async def test_get_stats_today_orders(
        self,
        companion_client,
        seed_companion_profile,
        seed_hospital,
        seed_order,
        seed_user,
    ):
        companion = companion_client._test_user
        await seed_companion_profile(companion.id)
        patient = await seed_user(phone="13600136001", role=UserRole.patient)
        hospital = await seed_hospital()

        # Created today — should count
        await seed_order(
            patient.id,
            hospital.id,
            companion_id=companion.id,
            status=OrderStatus.accepted,
        )

        resp = await companion_client.get("/api/v1/companions/me/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert data["today_orders"] >= 1
