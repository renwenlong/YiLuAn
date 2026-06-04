"""S2-REQ-003-P2: admin/service-packages CRUD endpoints 单测.

覆盖：
- list (默认仅 active / include_inactive=true 拉全)
- get 单条 + 404
- create 成功 + 唯一 code 冲突 409 + price 校验 + audit 写入
- patch 部分更新 + 404 + 空 body 400 + audit before/after diff
- delete 软删 + 已软删幂等 + audit 写入
- 鉴权失败 (无 X-Admin-Token → 401/403)
"""

import json
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.service_package import ServicePackage
from tests.conftest import test_session_factory

BASE = "/api/v1/admin/service-packages"


async def _seed_pkg(
    code: str = "test_pkg",
    name: str = "测试档位",
    price: Decimal = Decimal("199.00"),
    sort_order: int = 100,
    is_active: bool = True,
    description: str | None = None,
) -> uuid.UUID:
    pkg_id = uuid.uuid4()
    async with test_session_factory() as session:
        pkg = ServicePackage(
            id=pkg_id,
            code=code,
            name=name,
            price=price,
            sort_order=sort_order,
            is_active=is_active,
            description=description,
        )
        session.add(pkg)
        await session.commit()
    return pkg_id


async def _audit_rows_for(target_id: uuid.UUID) -> list[AdminAuditLog]:
    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog)
            .where(AdminAuditLog.target_id == target_id)
            .order_by(AdminAuditLog.created_at.asc())
        )
        return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_requires_admin_token(client):
    """无 X-Admin-Token / JWT 应 401 或 403。"""
    resp = await client.get(f"{BASE}/")
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_default_only_active(admin_client):
    await _seed_pkg(code="active_a", name="启用 A", sort_order=10)
    await _seed_pkg(
        code="inactive_b", name="禁用 B", sort_order=20, is_active=False
    )

    resp = await admin_client.get(f"{BASE}/")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    codes = [it["code"] for it in data["items"]]
    assert "active_a" in codes
    assert "inactive_b" not in codes
    assert data["total"] == len([c for c in codes])


@pytest.mark.asyncio
async def test_list_include_inactive(admin_client):
    await _seed_pkg(code="active_c", name="启用 C", sort_order=10)
    await _seed_pkg(
        code="inactive_d", name="禁用 D", sort_order=20, is_active=False
    )

    resp = await admin_client.get(f"{BASE}/?include_inactive=true")
    assert resp.status_code == 200
    codes = [it["code"] for it in resp.json()["items"]]
    assert "active_c" in codes
    assert "inactive_d" in codes


@pytest.mark.asyncio
async def test_list_sorted_by_sort_order_asc(admin_client):
    await _seed_pkg(code="pkg_z", name="Z", sort_order=300)
    await _seed_pkg(code="pkg_a", name="A", sort_order=100)
    await _seed_pkg(code="pkg_m", name="M", sort_order=200)

    resp = await admin_client.get(f"{BASE}/")
    assert resp.status_code == 200
    seen = [it["code"] for it in resp.json()["items"]]
    a_idx = seen.index("pkg_a")
    m_idx = seen.index("pkg_m")
    z_idx = seen.index("pkg_z")
    assert a_idx < m_idx < z_idx


# ---------------------------------------------------------------------------
# Get single
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_ok(admin_client):
    pkg_id = await _seed_pkg(code="get_one", name="获取一项", price=Decimal("88.00"))
    resp = await admin_client.get(f"{BASE}/{pkg_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == str(pkg_id)
    assert data["code"] == "get_one"
    assert Decimal(data["price"]) == Decimal("88.00")


@pytest.mark.asyncio
async def test_get_404_when_missing(admin_client):
    resp = await admin_client.get(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_ok_and_audit(admin_client):
    body = {
        "code": "vip_companion",
        "name": "VIP 全程陪诊",
        "price": "399.00",
        "sort_order": 5,
        "description": "VIP 档",
        "is_active": True,
    }
    resp = await admin_client.post(f"{BASE}/", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["code"] == "vip_companion"
    assert Decimal(data["price"]) == Decimal("399.00")
    new_id = uuid.UUID(data["id"])

    audits = await _audit_rows_for(new_id)
    assert len(audits) == 1
    log = audits[0]
    assert log.action == "service_package_create"
    assert log.target_type == "service_package"
    payload = json.loads(log.reason)
    assert payload["action"] == "create"
    assert payload["before"] is None
    assert payload["after"]["code"] == "vip_companion"
    assert payload["after"]["price"] == "399.00"


@pytest.mark.asyncio
async def test_create_conflict_when_code_duplicate(admin_client):
    await _seed_pkg(code="dup_code", name="原档")
    body = {"code": "dup_code", "name": "重复", "price": "10.00"}
    resp = await admin_client.post(f"{BASE}/", json=body)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_create_rejects_zero_price(admin_client):
    body = {"code": "free_pkg", "name": "免费", "price": "0.00"}
    resp = await admin_client.post(f"{BASE}/", json=body)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_create_rejects_negative_sort_order(admin_client):
    body = {
        "code": "neg_sort",
        "name": "负序",
        "price": "10.00",
        "sort_order": -1,
    }
    resp = await admin_client.post(f"{BASE}/", json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Patch (update)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_patch_partial_update_price_and_audit_diff(admin_client):
    pkg_id = await _seed_pkg(
        code="patch_pkg", name="老名", price=Decimal("100.00"), sort_order=50
    )
    resp = await admin_client.patch(
        f"{BASE}/{pkg_id}", json={"price": "150.50", "name": "新名"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert Decimal(data["price"]) == Decimal("150.50")
    assert data["name"] == "新名"

    audits = await _audit_rows_for(pkg_id)
    update_logs = [a for a in audits if a.action == "service_package_update"]
    assert len(update_logs) == 1
    payload = json.loads(update_logs[0].reason)
    assert payload["before"]["price"] == "100.00"
    assert payload["before"]["name"] == "老名"
    assert payload["after"]["price"] == "150.50"
    assert payload["after"]["name"] == "新名"


@pytest.mark.asyncio
async def test_patch_404_when_missing(admin_client):
    resp = await admin_client.patch(
        f"{BASE}/{uuid.uuid4()}", json={"price": "1.00"}
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_empty_body_400(admin_client):
    pkg_id = await _seed_pkg(code="patch_empty", name="x")
    resp = await admin_client.patch(f"{BASE}/{pkg_id}", json={})
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Delete (soft)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_soft_delete_sets_is_active_false_and_audit(admin_client):
    pkg_id = await _seed_pkg(code="to_softdel", name="待软删", is_active=True)

    resp = await admin_client.delete(f"{BASE}/{pkg_id}")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    # DB row 仍在，仅 is_active=false
    async with test_session_factory() as session:
        pkg = await session.get(ServicePackage, pkg_id)
        assert pkg is not None
        assert pkg.is_active is False

    audits = await _audit_rows_for(pkg_id)
    del_logs = [a for a in audits if a.action == "service_package_soft_delete"]
    assert len(del_logs) == 1
    payload = json.loads(del_logs[0].reason)
    assert payload["before"]["is_active"] is True
    assert payload["after"]["is_active"] is False


@pytest.mark.asyncio
async def test_soft_delete_idempotent_when_already_inactive(admin_client):
    pkg_id = await _seed_pkg(code="already_off", name="已禁", is_active=False)

    resp = await admin_client.delete(f"{BASE}/{pkg_id}")
    assert resp.status_code == 200

    audits = await _audit_rows_for(pkg_id)
    del_logs = [a for a in audits if a.action == "service_package_soft_delete"]
    assert len(del_logs) == 1  # 仍写 audit 留痕
    payload = json.loads(del_logs[0].reason)
    assert payload["action"] == "soft_delete_noop_already_inactive"


@pytest.mark.asyncio
async def test_soft_delete_404_when_missing(admin_client):
    resp = await admin_client.delete(f"{BASE}/{uuid.uuid4()}")
    assert resp.status_code == 404
