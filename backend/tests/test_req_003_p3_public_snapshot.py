"""S2-REQ-003-P3 / ADR-0043 §3 acceptance tests.

覆盖:
  AC1: GET /api/v1/public/service-packages 公开 + sort_order 升序 + active only
  AC2: create_order 事务内 SELECT FOR UPDATE 锁档位 (独立 race 用例)
  AC3: Order 写入 service_name/price_snapshot 非空 (与 service_packages 一致)
  AC4: 支付/退款金额读 service_price_snapshot (在 test_orders 底层验证續纱)
  AC5: 下架/不存在 service_type 起单 → 400 SERVICE_PACKAGE_INVALID
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.order import Order
from app.models.service_package import ServicePackage


@pytest.mark.asyncio
class TestPublicServicePackages:
    async def test_public_list_returns_active_sorted(self, client: AsyncClient):
        """AC1: 公开访问 + 按 sort_order 升序 + active only."""
        resp = await client.get("/api/v1/public/service-packages")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 3
        # sort_order 升序 → full_accompany(10) / half_accompany(20) / errand(30)
        codes = [pkg["code"] for pkg in data]
        assert codes == ["full_accompany", "half_accompany", "errand"]
        # 价格一致
        full = next(p for p in data if p["code"] == "full_accompany")
        assert Decimal(str(full["price"])) == Decimal("299.00")
        assert full["name"] == "全程陪诊"

    async def test_public_list_no_auth_required(self, client: AsyncClient):
        """AC1: 不传 Authorization header 仍能访问."""
        resp = await client.get("/api/v1/public/service-packages")
        assert resp.status_code == 200

    async def test_public_list_skips_inactive(
        self, client: AsyncClient
    ):
        """AC1: is_active=False 不返回."""
        # 把 errand 改为 inactive
        from tests.conftest import test_session_factory
        async with test_session_factory() as session:
            result = await session.execute(
                select(ServicePackage).where(ServicePackage.code == "errand")
            )
            pkg = result.scalar_one()
            pkg.is_active = False
            await session.commit()

        resp = await client.get("/api/v1/public/service-packages")
        assert resp.status_code == 200
        codes = [p["code"] for p in resp.json()]
        assert "errand" not in codes
        assert len(codes) == 2


@pytest.mark.asyncio
class TestCreateOrderSnapshot:
    async def test_create_order_writes_snapshot(
        self, authenticated_client, seed_hospital
    ):
        """AC3: 下单后 Order.service_name/price_snapshot 与 service_packages 一致."""
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "hospital_id": str(hospital.id),
                "service_type": "full_accompany",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "description": "P3 snapshot test",
            },
        )
        assert resp.status_code in (200, 201), resp.text
        order_data = resp.json()
        # API 应返回 price (兼容 iOS)
        assert Decimal(str(order_data["price"])) == Decimal("299.00")
        # S2-BUG-S010-01: API 应暴露 snapshot 字段 (不能靠 DB 查)
        assert order_data.get("service_name_snapshot") == "全程陪诊"
        assert Decimal(str(order_data["service_price_snapshot"])) == Decimal("299.00")
        # 数据库查 snapshot 字段 (双验)
        from tests.conftest import test_session_factory
        async with test_session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.order_number == order_data["order_number"])
            )).scalar_one()
            assert order.service_name_snapshot == "全程陪诊"
            assert order.service_price_snapshot == Decimal("299.00")

    async def test_create_order_rejects_inactive_package(
        self, authenticated_client, seed_hospital
    ):
        """AC5: 档位下架 → 400 SERVICE_PACKAGE_INVALID."""
        # 把 full_accompany 改 inactive
        from tests.conftest import test_session_factory
        async with test_session_factory() as session:
            pkg = (await session.execute(
                select(ServicePackage).where(ServicePackage.code == "full_accompany")
            )).scalar_one()
            pkg.is_active = False
            await session.commit()

        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "hospital_id": str(hospital.id),
                "service_type": "full_accompany",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "description": "inactive pkg",
            },
        )
        assert resp.status_code == 400, resp.text
        body = resp.json()
        # error_code 可能在 detail / code 或 detail.error_code
        body_str = str(body)
        assert "SERVICE_PACKAGE_INVALID" in body_str or "下架" in body_str

    async def test_create_order_uses_current_pkg_price(
        self, authenticated_client, seed_hospital
    ):
        """AC2 简化 race: admin 改价后下单, 快照为新价格."""
        # admin 改价 full_accompany → 399
        from tests.conftest import test_session_factory
        async with test_session_factory() as session:
            pkg = (await session.execute(
                select(ServicePackage).where(ServicePackage.code == "full_accompany")
            )).scalar_one()
            pkg.price = Decimal("399.00")
            await session.commit()

        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "hospital_id": str(hospital.id),
                "service_type": "full_accompany",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "description": "after price hike",
            },
        )
        assert resp.status_code in (200, 201)
        order_data = resp.json()
        assert Decimal(str(order_data["price"])) == Decimal("399.00")

        async with test_session_factory() as session:
            order = (await session.execute(
                select(Order).where(Order.order_number == order_data["order_number"])
            )).scalar_one()
            assert order.service_price_snapshot == Decimal("399.00")


@pytest.mark.asyncio
class TestAdminOrderItemSnapshot:
    """S2-BUG-S010-02: admin/orders/{id} OrderItem schema 须暴露 snapshot 字段."""

    async def test_admin_order_detail_returns_snapshot(
        self, authenticated_client, admin_client, seed_hospital
    ):
        # 患者侧下单
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "hospital_id": str(hospital.id),
                "service_type": "full_accompany",
                "appointment_date": "2026-12-01",
                "appointment_time": "09:00",
                "description": "admin snapshot test",
            },
        )
        assert resp.status_code in (200, 201), resp.text
        order_id = resp.json()["id"]

        # admin 端拉 detail
        admin_resp = await admin_client.get(f"/api/v1/admin/orders/{order_id}")
        assert admin_resp.status_code == 200, admin_resp.text
        data = admin_resp.json()
        # S2-BUG-S010-02 fix: admin OrderItem 须返 snapshot
        assert data.get("service_name_snapshot") == "全程陪诊", \
            f"admin OrderItem 缺 service_name_snapshot: {data}"
        assert data.get("service_price_snapshot") == "299.00", \
            f"admin OrderItem 缺 service_price_snapshot: {data}"

    async def test_admin_order_list_returns_snapshot(
        self, authenticated_client, admin_client, seed_hospital
    ):
        hospital = await seed_hospital()
        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "hospital_id": str(hospital.id),
                "service_type": "half_accompany",
                "appointment_date": "2026-12-02",
                "appointment_time": "10:00",
                "description": "list snapshot",
            },
        )
        assert resp.status_code in (200, 201)
        # admin list (no trailing slash)
        list_resp = await admin_client.get("/api/v1/admin/orders", follow_redirects=True)
        assert list_resp.status_code == 200, list_resp.text
        items = list_resp.json().get("items", [])
        assert items, "admin list 应至少含 1 单"
        # 至少有一行 service_name_snapshot 非空 (新订单 snapshot 必填)
        any_with_snap = any(it.get("service_name_snapshot") for it in items)
        assert any_with_snap, \
            "admin list OrderItem 须返 service_name_snapshot"
