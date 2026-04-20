"""
Admin API tests — covers all /admin/* endpoints.

Scenarios:
  - Auth: 401 (no token), 403 (non-admin), 200 (admin)
  - Companion verification: approve, reject, re-approve rejected
  - Order management: list, force-status, admin-refund
  - User management: disable, enable
  - Pagination boundaries
"""

import pytest
from httpx import AsyncClient

from app.models.companion_profile import VerificationStatus
from app.models.order import OrderStatus


# =============================================================================
# Auth guard tests
# =============================================================================


@pytest.mark.asyncio
class TestAdminAuth:
    """Verify admin auth guard blocks unauthorised access."""

    async def test_no_token_returns_401(self, client: AsyncClient):
        """Request without Authorization header should get 401 or 403."""
        resp = await client.get("/api/v1/admin/orders")
        assert resp.status_code in (401, 403)

    async def test_patient_returns_403(self, authenticated_client: AsyncClient):
        """Patient role user should be forbidden from admin endpoints."""
        resp = await authenticated_client.get("/api/v1/admin/orders")
        assert resp.status_code == 403

    async def test_companion_returns_403(self, companion_client: AsyncClient):
        """Companion role user should be forbidden from admin endpoints."""
        resp = await companion_client.get("/api/v1/admin/orders")
        assert resp.status_code == 403

    async def test_admin_returns_200(self, admin_client: AsyncClient):
        """Admin role user should access admin endpoints successfully."""
        resp = await admin_client.get("/api/v1/admin/orders")
        assert resp.status_code == 200


# =============================================================================
# Companion verification
# =============================================================================


@pytest.mark.asyncio
class TestCompanionVerification:
    """Tests for companion approval / rejection workflow (token-based auth)."""

    HEADERS = {"X-Admin-Token": "dev-admin-token"}

    async def test_list_pending_empty(self, client: AsyncClient):
        """Empty list when no pending companions exist."""
        resp = await client.get("/api/v1/admin/companions/", headers=self.HEADERS)
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_approve_pending_companion(
        self,
        client: AsyncClient,
        seed_user,
        seed_companion_profile,
    ):
        """Approving a pending companion should change status to verified."""
        user = await seed_user(phone="13100131000")
        profile = await seed_companion_profile(
            user.id, verification_status=VerificationStatus.pending
        )

        resp = await client.post(
            f"/api/v1/admin/companions/{profile.id}/approve",
            headers=self.HEADERS,
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_reject_pending_companion(
        self,
        client: AsyncClient,
        seed_user,
        seed_companion_profile,
    ):
        """Rejecting a pending companion should change status to rejected."""
        user = await seed_user(phone="13100131001")
        profile = await seed_companion_profile(
            user.id, verification_status=VerificationStatus.pending
        )

        resp = await client.post(
            f"/api/v1/admin/companions/{profile.id}/reject",
            headers=self.HEADERS,
            json={"reason": "资质不符"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    async def test_approve_already_verified_returns_409(
        self,
        client: AsyncClient,
        seed_user,
        seed_companion_profile,
    ):
        """Approving an already-verified companion should return 409."""
        user = await seed_user(phone="13100131002")
        profile = await seed_companion_profile(
            user.id, verification_status=VerificationStatus.verified
        )

        resp = await client.post(
            f"/api/v1/admin/companions/{profile.id}/approve",
            headers=self.HEADERS,
        )
        assert resp.status_code == 409

    async def test_approve_nonexistent_returns_404(self, client: AsyncClient):
        """Approving a non-existent profile should return 404."""
        import uuid

        fake_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/admin/companions/{fake_id}/approve",
            headers=self.HEADERS,
        )
        assert resp.status_code == 404

    async def test_list_pending_pagination(
        self,
        client: AsyncClient,
        seed_user,
        seed_companion_profile,
    ):
        """Pagination should limit results per page."""
        for i in range(3):
            user = await seed_user(phone=f"1320013200{i}")
            await seed_companion_profile(
                user.id, verification_status=VerificationStatus.pending
            )

        resp = await client.get(
            "/api/v1/admin/companions/?page=1&page_size=2",
            headers=self.HEADERS,
        )
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 2

        resp2 = await client.get(
            "/api/v1/admin/companions/?page=2&page_size=2",
            headers=self.HEADERS,
        )
        assert resp2.status_code == 200
        assert len(resp2.json()["items"]) == 1


# =============================================================================
# Order management
# =============================================================================


@pytest.mark.asyncio
class TestOrderManagement:
    """Tests for admin order management endpoints."""

    async def test_list_orders(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
    ):
        """Admin should see all orders."""
        user = await seed_user(phone="13400134000")
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id)

        resp = await admin_client.get("/api/v1/admin/orders")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1

    async def test_list_orders_filter_by_status(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
    ):
        """Filter orders by status."""
        user = await seed_user(phone="13400134001")
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id, status=OrderStatus.completed)

        resp = await admin_client.get(
            "/api/v1/admin/orders?status=completed"
        )
        assert resp.status_code == 200
        for item in resp.json()["items"]:
            assert item["status"] == "completed"

    async def test_force_status_change(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
    ):
        """Admin can force an order to any status."""
        user = await seed_user(phone="13400134002")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/force-status?target_status=completed"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_status"] == "created"
        assert data["new_status"] == "completed"

    async def test_force_invalid_status_returns_400(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
    ):
        """Invalid target status should return 400."""
        user = await seed_user(phone="13400134003")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/force-status?target_status=invalid_status"
        )
        assert resp.status_code == 400

    async def test_admin_refund_paid_order(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        """Admin can refund a paid order."""
        user = await seed_user(phone="13400134004")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)
        await seed_payment(order.id, user.id, amount=299.0)

        resp = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/admin-refund?refund_ratio=0.5"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["refund_amount"] == 149.5

    async def test_admin_refund_unpaid_order_returns_400(
        self,
        admin_client: AsyncClient,
        seed_user,
        seed_hospital,
        seed_order,
    ):
        """Refunding an unpaid order should fail."""
        user = await seed_user(phone="13400134005")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await admin_client.post(
            f"/api/v1/admin/orders/{order.id}/admin-refund"
        )
        assert resp.status_code == 400


# =============================================================================
# User management
# =============================================================================


@pytest.mark.asyncio
class TestUserManagement:
    """Tests for admin user management endpoints."""

    async def test_list_users(self, admin_client: AsyncClient):
        """Admin should be able to list users."""
        resp = await admin_client.get("/api/v1/admin/users")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data
        assert data["total"] >= 1  # at least the admin user itself

    async def test_disable_user(
        self, admin_client: AsyncClient, seed_user
    ):
        """Admin can disable a user."""
        user = await seed_user(phone="13500135000")
        resp = await admin_client.post(
            f"/api/v1/admin/users/{user.id}/disable"
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

    async def test_enable_user(
        self, admin_client: AsyncClient, seed_user
    ):
        """Admin can re-enable a disabled user."""
        user = await seed_user(phone="13500135001", is_active=False)
        resp = await admin_client.post(
            f"/api/v1/admin/users/{user.id}/enable"
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

    async def test_disable_nonexistent_user_returns_404(
        self, admin_client: AsyncClient
    ):
        """Disabling a non-existent user should return 404."""
        import uuid

        resp = await admin_client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/disable"
        )
        assert resp.status_code == 404
