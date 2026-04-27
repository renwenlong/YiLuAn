"""
Admin API tests - covers the new token-auth /admin/* endpoints (B4).

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

        # phone column filter still uses raw value; default response phone is masked
        resp = await client.get(
            "/api/v1/admin/users?phone=18811", headers=HEADERS
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert items
        # default => masked; raw 18811 prefix is no longer in `phone`,
        # but masked form still leaks the leading 3 digits (188).
        assert all("188" in (u["phone"] or "") for u in items)
        assert all("*" in (u["phone"] or "") for u in items)

        # ?reveal=true must restore the raw phone (and write reveal_pii audit).
        resp2 = await client.get(
            "/api/v1/admin/users?phone=18811&reveal=true", headers=HEADERS
        )
        items2 = resp2.json()["items"]
        assert all("18811" in (u["phone"] or "") for u in items2)

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


# Make sure UserRole import isn't elided by linters - used implicitly when
# seed_user creates patient/companion accounts in fixtures.
_ = UserRole


# =============================================================================
# W18 admin-h5 contract: display_name / phone_masked / reveal / read-audit /
# force-status deny-list
# =============================================================================


@pytest.mark.asyncio
class TestAdminH5Contract:
    async def test_list_orders_returns_patient_display_name_and_masked_phone(
        self, client, seed_user, seed_hospital, seed_order
    ):
        async with test_session_factory() as session:
            user = User(
                phone="13800138000",
                roles="patient",
                is_active=True,
                display_name="陈七叔",
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id)

        resp = await client.get(
            f"/api/v1/admin/orders?patient_id={user.id}", headers=HEADERS
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert items
        item = items[0]
        assert item["patient_display_name"] == "陈七叔"
        # masked: keeps prefix, hides middle, exposes last 2 digits
        masked = item["patient_phone_masked"]
        assert masked
        assert masked.startswith("138") and masked.endswith("00") and "*" in masked
        assert masked != "13800138000"
        # `price` field replaces legacy `amount`
        assert "price" in item
        assert item["price"].endswith(".00")

    @pytest.mark.parametrize(
        "status_value",
        ["created", "in_progress", "cancelled_by_patient"],
    )
    async def test_list_orders_with_real_status_enum_filter(
        self, client, seed_user, seed_hospital, seed_order, status_value
    ):
        user = await seed_user(phone=f"137001370{hash(status_value) % 100:02d}")
        hospital = await seed_hospital()
        await seed_order(user.id, hospital.id, status=OrderStatus(status_value))

        resp = await client.get(
            f"/api/v1/admin/orders?status={status_value}", headers=HEADERS
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()["items"]
        assert all(it["status"] == status_value for it in items)

    async def test_users_filter_by_is_active_query_param(
        self, client, seed_user
    ):
        await seed_user(phone="13900139001", is_active=True)
        await seed_user(phone="13900139002", is_active=False)

        resp_t = await client.get(
            "/api/v1/admin/users?is_active=true", headers=HEADERS
        )
        assert resp_t.status_code == 200
        assert all(u["is_active"] is True for u in resp_t.json()["items"])

        resp_f = await client.get(
            "/api/v1/admin/users?is_active=false", headers=HEADERS
        )
        assert resp_f.status_code == 200
        items_f = resp_f.json()["items"]
        assert items_f
        assert all(u["is_active"] is False for u in items_f)

    async def test_user_phone_masked_by_default(self, client, seed_user):
        user = await seed_user(phone="13812345678")
        resp = await client.get(
            f"/api/v1/admin/users/{user.id}", headers=HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["phone"] != "13812345678"
        assert "*" in (body["phone"] or "")
        # phone_masked is always present and always masked
        assert body["phone_masked"]
        assert "*" in body["phone_masked"]

    async def test_user_phone_revealed_with_reveal_param_writes_audit(
        self, client, seed_user
    ):
        user = await seed_user(phone="13888888888")
        resp = await client.get(
            f"/api/v1/admin/users/{user.id}?reveal=true", headers=HEADERS
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["phone"] == "13888888888"
        # phone_masked still masked even when revealed
        assert "*" in body["phone_masked"]

        async with test_session_factory() as session:
            logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == user.id,
                        AdminAuditLog.action == "reveal_pii",
                    )
                )
            ).scalars().all()
            assert len(logs) == 1
            assert "phone" in (logs[0].reason or "")

    async def test_force_status_completed_to_created_returns_400_and_writes_denied_audit(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13700137100")
        hospital = await seed_hospital()
        order = await seed_order(
            user.id, hospital.id, status=OrderStatus.completed
        )

        resp = await client.post(
            f"/api/v1/admin/orders/{order.id}/force-status",
            headers=HEADERS,
            json={"status": "created", "reason": "误操作回退"},
        )
        assert resp.status_code == 400
        assert "Forbidden" in resp.text or "forbidden" in resp.text

        async with test_session_factory() as session:
            denied_logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "force_status_denied",
                    )
                )
            ).scalars().all()
            assert len(denied_logs) == 1
            # ensure the original force_status was NOT applied
            applied = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "force_status",
                    )
                )
            ).scalars().all()
            assert len(applied) == 0

    async def test_view_endpoints_write_audit_with_summary_payload(
        self, client, seed_user, seed_hospital, seed_order
    ):
        user = await seed_user(phone="13700137200")
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # list call — emits one summary view_orders_list row
        list_resp = await client.get(
            "/api/v1/admin/orders?status=created&page=1&page_size=10",
            headers=HEADERS,
        )
        assert list_resp.status_code == 200

        # detail call — emits view_order_detail with target_id=order.id
        detail_resp = await client.get(
            f"/api/v1/admin/orders/{order.id}", headers=HEADERS
        )
        assert detail_resp.status_code == 200

        # users list
        users_list = await client.get(
            "/api/v1/admin/users?role=patient", headers=HEADERS
        )
        assert users_list.status_code == 200

        # user detail
        user_detail = await client.get(
            f"/api/v1/admin/users/{user.id}", headers=HEADERS
        )
        assert user_detail.status_code == 200

        async with test_session_factory() as session:
            list_orders_logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.action == "view_orders_list",
                    )
                )
            ).scalars().all()
            assert len(list_orders_logs) >= 1
            assert any(
                "status=created" in (log.reason or "") and "page=1" in (log.reason or "")
                for log in list_orders_logs
            )

            detail_logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == order.id,
                        AdminAuditLog.action == "view_order_detail",
                    )
                )
            ).scalars().all()
            assert len(detail_logs) == 1

            users_list_logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.action == "view_users_list",
                    )
                )
            ).scalars().all()
            assert len(users_list_logs) >= 1

            user_detail_logs = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_id == user.id,
                        AdminAuditLog.action == "view_user_detail",
                    )
                )
            ).scalars().all()
            assert len(user_detail_logs) == 1
