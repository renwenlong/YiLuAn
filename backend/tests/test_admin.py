"""
Admin API tests — covers the new token-auth /admin/* endpoints (B4).

Auth model
----------
All admin routes now require the ``X-Admin-Token`` header; the legacy
JWT/role-based dependency was removed. Tests inject the dev token
(``dev-admin-token``, configured via ``settings.admin_api_token``).

Scopes covered:
  - Auth guard: missing / wrong token
  - Order management: list (filters), detail, force-status, refund
  - User management: list (filters), detail, disable, enable
  - Audit log writes for every mutating endpoint
"""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.order import OrderStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory

ADMIN_TOKEN = "dev-admin-token"
HEADERS = {"X-Admin-Token": ADMIN_TOKEN}


# =============================================================================
# Auth guard
# =============================================================================


@pytest.mark.asyncio
class TestAdminAuth:
    async def test_orders_no_token_returns_422(self, client: AsyncClient):
        # FastAPI rejects requests missing a required Header dependency
        # with 422 (validation error), matching companions module behaviour.
        resp = await client.get("/api/v1/admin/orders")
        assert resp.status_code == 422

    async def test_orders_wrong_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/admin/orders", headers={"X-Admin-Token": "bad"}
        )
        assert resp.status_code == 401

    async def test_users_no_token_returns_422(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/users")
        assert resp.status_code == 422

    async def test_users_wrong_token_returns_401(self, client: AsyncClient):
        resp = await client.get(
            "/api/v1/admin/users", headers={"X-Admin-Token": "bad"}
        )
        assert resp.status_code == 401


# =============================================================================
# Order management
# =============================================================================


@pytest.mark.asyncio
class TestAdminOrders:
    async def test_list_orders(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134000")
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id)

        resp = await client.get("/api/v1/admin/orders", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "items" in data and isinstance(data["items"], list)
        assert "page" in data and "page_size" in data

    async def test_list_orders_filter_by_status(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134001")
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id, status=OrderStatus.completed)
        await seed_order(user.id, hospital.id, status=OrderStatus.created)

        resp = await client.get(
            "/api/v1/admin/orders?status=completed", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert all(item["status"] == "completed" for item in items)

    async def test_list_orders_filter_by_patient(
        self, client, seed_user, seed_hospital, seed_order
    ):
        u1 = await seed_user(phone="13400134010")
        u2 = await seed_user(phone="13400134011")
        hospital = await seed_hospital()
        await seed_order(u1.id, hospital.id)
        await seed_order(u2.id, hospital.id)

        resp = await client.get(
            f"/api/v1/admin/orders?patient_id={u1.id}", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items
        assert all(item["patient_id"] == str(u1.id) for item in items)

    async def test_list_orders_invalid_status_returns_400(self, client):
        resp = await client.get(
            "/api/v1/admin/orders?status=not-a-status", headers=HEADERS
        )
        assert resp.status_code == 400

    async def test_list_orders_pagination(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134020")
        hospital = await seed_hospital()
        for _ in range(3):
            await seed_order(user.id, hospital.id)

        resp = await client.get(
            f"/api/v1/admin/orders?patient_id={user.id}&page=1&page_size=2",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page_size"] == 2

    async def test_get_order_detail(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134030")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await client.get(
            f"/api/v1/admin/orders/{order.id}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(order.id)

    async def test_get_order_not_found(self, client):
        resp = await client.get(
            f"/api/v1/admin/orders/{uuid.uuid4()}", headers=HEADERS
        )
        assert resp.status_code == 404

    async def test_force_status(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134040")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "completed", "reason": "运营干预"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["old_status"] == "created"
        assert data["new_status"] == "completed"

        # Audit log written
        async with test_session_factory() as session:
            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "force_status",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            assert "运营干预" in logs[0].reason

    async def test_force_status_invalid_returns_400(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134041")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "totally-bogus", "reason": "x"},
        )
        assert resp.status_code == 400

    async def test_force_status_missing_reason_422(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134042")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "completed"},
        )
        assert resp.status_code == 422

    async def test_force_status_not_found(self, client):
        resp = await client.post(
            f"/api/v1/admin/orders/{uuid.uuid4()}/force-status",
            headers=HEADERS,
            json={"status": "completed", "reason": "x"},
        )
        assert resp.status_code == 404

    async def test_refund_happy_path(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        user = await seed_user(phone="13400134050")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )
        await seed_payment(order.id, user.id, amount=299.0)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "100.00", "reason": "客户投诉"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["refund_amount"] == "100.00"
        assert data["payment_id"]

        async with test_session_factory() as session:
            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "refund",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            assert "100.00" in logs[0].reason

    async def test_refund_unrefundable_status_returns_400(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134051")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.created
        )

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "1.00", "reason": "x"},
        )
        assert resp.status_code == 400

    async def test_refund_unpaid_returns_400(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13400134052")
        hospital = await seed_hospital()
        # Status is refundable but no Payment row exists.
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "10.00", "reason": "x"},
        )
        assert resp.status_code == 400

    async def test_refund_amount_exceeds_paid_returns_400(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        user = await seed_user(phone="13400134053")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )
        await seed_payment(order.id, user.id, amount=50.0)

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "999.00", "reason": "x"},
        )
        assert resp.status_code == 400

    async def test_refund_idempotent_second_call_returns_400(
        self,
        client,
        seed_user,
        seed_hospital,
        seed_order,
        seed_payment,
    ):
        user = await seed_user(phone="13400134054")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )
        await seed_payment(order.id, user.id, amount=299.0)

        first = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "50.00", "reason": "round 1"},
        )
        assert first.status_code == 200

        second = await client.post(
            f"/api/v1/admin/orders/{order.id}/refund",
            headers=HEADERS,
            json={"amount": "50.00", "reason": "round 2"},
        )
        assert second.status_code == 400

    async def test_refund_not_found(self, client):
        resp = await client.post(
            f"/api/v1/admin/orders/{uuid.uuid4()}/refund",
            headers=HEADERS,
            json={"amount": "1.00", "reason": "x"},
        )
        assert resp.status_code == 404


# =============================================================================
# User management
# =============================================================================


@pytest.mark.asyncio
class TestAdminUsers:
    async def test_list_users(self, client, seed_user):
        await seed_user(phone="13500135100")
        resp = await client.get("/api/v1/admin/users", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1
        assert "items" in data

    async def test_list_users_filter_phone(self, client, seed_user):
        await seed_user(phone="18811112222")
        await seed_user(phone="13500135101")

        resp = await client.get(
            "/api/v1/admin/users?phone=18811", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items
        assert all("18811" in (u["phone"] or "") for u in items)

    async def test_list_users_filter_is_active(self, client, seed_user):
        await seed_user(phone="13500135102", is_active=False)
        resp = await client.get(
            "/api/v1/admin/users?is_active=false", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items
        assert all(u["is_active"] is False for u in items)

    async def test_list_users_pagination(self, client, seed_user):
        for i in range(3):
            await seed_user(phone=f"1700017{i:04d}")

        resp = await client.get(
            "/api/v1/admin/users?phone=170001&page=1&page_size=2",
            headers=HEADERS,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["page_size"] == 2
        assert len(data["items"]) <= 2

    async def test_get_user_detail(self, client, seed_user):
        user = await seed_user(phone="13500135103")
        resp = await client.get(
            f"/api/v1/admin/users/{user.id}", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["id"] == str(user.id)

    async def test_get_user_not_found(self, client):
        resp = await client.get(
            f"/api/v1/admin/users/{uuid.uuid4()}", headers=HEADERS
        )
        assert resp.status_code == 404

    async def test_disable_user(self, client, seed_user):
        user = await seed_user(phone="13500135200")
        resp = await client.post(
            f"/api/v1/admin/users/{user.id}/disable",
            headers=HEADERS,
            json={"reason": "高风险账号"},
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        async with test_session_factory() as session:
            refreshed = await session.get(User, user.id)
            assert refreshed.is_active is False

            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == user.id,
                        AdminAuditLog.action == "disable",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            assert logs[0].reason == "高风险账号"

    async def test_disable_missing_reason_422(self, client, seed_user):
        user = await seed_user(phone="13500135201")
        resp = await client.post(
            f"/api/v1/admin/users/{user.id}/disable",
            headers=HEADERS,
            json={},
        )
        assert resp.status_code == 422

    async def test_disable_user_not_found(self, client):
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/disable",
            headers=HEADERS,
            json={"reason": "x"},
        )
        assert resp.status_code == 404

    async def test_enable_user(self, client, seed_user):
        user = await seed_user(phone="13500135300", is_active=False)
        resp = await client.post(
            f"/api/v1/admin/users/{user.id}/enable", headers=HEADERS
        )
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

        async with test_session_factory() as session:
            refreshed = await session.get(User, user.id)
            assert refreshed.is_active is True

            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == user.id,
                        AdminAuditLog.action == "enable",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1

    async def test_enable_user_not_found(self, client):
        resp = await client.post(
            f"/api/v1/admin/users/{uuid.uuid4()}/enable", headers=HEADERS
        )
        assert resp.status_code == 404


# Make sure UserRole import isn't elided by linters — used implicitly when
# seed_user creates patient/companion accounts in fixtures.
_ = UserRole
