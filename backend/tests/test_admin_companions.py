"""
Tests for admin companions audit endpoints (B1).

Covers: auth (token), list, approve, reject, edge cases.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory

ADMIN_TOKEN = "dev-admin-token"
BASE = "/api/v1/admin/companions"


def _headers(token: str | None = ADMIN_TOKEN) -> dict:
    if token is None:
        return {}
    return {"X-Admin-Token": token}


async def _create_profile(
    verification_status: VerificationStatus = VerificationStatus.pending,
    real_name: str = "测试陪诊师",
    *,
    with_phone: bool = True,
) -> CompanionProfile:
    async with test_session_factory() as session:
        # 同时创建 User 记录（上架校验依赖代理 user.phone）
        user_id = uuid.uuid4()
        phone = f"138{uuid.uuid4().int % 100000000:08d}" if with_phone else None
        owner = User(
            id=user_id,
            phone=phone,
            role=UserRole.companion,
        )
        session.add(owner)
        profile = CompanionProfile(
            user_id=user_id,
            real_name=real_name,
            verification_status=verification_status,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


# ---- Auth ----


@pytest.mark.asyncio
async def test_no_token_returns_401(client):
    resp = await client.get(f"{BASE}/")
    assert resp.status_code == 401  # ADR-0034 dual-track auth


@pytest.mark.asyncio
async def test_wrong_token_returns_401(client):
    resp = await client.get(f"{BASE}/", headers=_headers("bad-token"))
    assert resp.status_code == 401
    assert "Invalid" in resp.json()["detail"]


# ---- List ----


@pytest.mark.asyncio
async def test_list_pending_only(client):
    """Should return only PENDING profiles."""
    await _create_profile(VerificationStatus.pending, "张三")
    await _create_profile(VerificationStatus.pending, "李四")
    await _create_profile(VerificationStatus.pending, "王五")
    await _create_profile(VerificationStatus.verified, "已通过")

    resp = await client.get(f"{BASE}/", headers=_headers())
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert len(data["items"]) == 3


@pytest.mark.asyncio
async def test_list_pagination(client):
    """Pagination: page_size=2, two pages."""
    for i in range(3):
        await _create_profile(VerificationStatus.pending, f"陪诊师{i}")

    resp1 = await client.get(
        f"{BASE}/", headers=_headers(), params={"page": 1, "page_size": 2}
    )
    data1 = resp1.json()
    assert len(data1["items"]) == 2
    assert data1["total"] == 3

    resp2 = await client.get(
        f"{BASE}/", headers=_headers(), params={"page": 2, "page_size": 2}
    )
    data2 = resp2.json()
    assert len(data2["items"]) == 1


# ---- Approve ----


@pytest.mark.asyncio
async def test_approve_happy_path(client):
    profile = await _create_profile()
    resp = await client.post(f"{BASE}/{profile.id}/approve", headers=_headers())
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

    # Verify status changed
    async with test_session_factory() as session:
        updated = await session.get(CompanionProfile, profile.id)
        assert updated.verification_status == VerificationStatus.verified

    # Verify audit log created
    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(AdminAuditLog.target_id == profile.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "approve"


@pytest.mark.asyncio
async def test_approve_already_approved_returns_409(client):
    profile = await _create_profile(VerificationStatus.verified)
    resp = await client.post(f"{BASE}/{profile.id}/approve", headers=_headers())
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_approve_not_found_returns_404(client):
    fake_id = uuid.uuid4()
    resp = await client.post(f"{BASE}/{fake_id}/approve", headers=_headers())
    assert resp.status_code == 404


# ---- Reject ----


@pytest.mark.asyncio
async def test_reject_happy_path(client):
    profile = await _create_profile()
    resp = await client.post(
        f"{BASE}/{profile.id}/reject",
        headers=_headers(),
        json={"reason": "资质不符"},
    )
    assert resp.status_code == 200

    # Verify status changed
    async with test_session_factory() as session:
        updated = await session.get(CompanionProfile, profile.id)
        assert updated.verification_status == VerificationStatus.rejected

    # Verify audit log
    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(AdminAuditLog.target_id == profile.id)
        )
        log = result.scalar_one()
        assert log.action == "reject"
        assert log.reason == "资质不符"


@pytest.mark.asyncio
async def test_reject_missing_reason_returns_422(client):
    profile = await _create_profile()
    resp = await client.post(
        f"{BASE}/{profile.id}/reject",
        headers=_headers(),
        json={},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# S2-DEV-013 PR-E1 (ADR-0044 §3.1): detail endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_companion_detail_returns_14_fields(client):
    """detail endpoint 返 14 字段 + cert_image_signed_url 占位 None (PR-E1)。"""
    profile = await _create_profile(real_name="详情测试陪诊师")

    # 写一些可选字段值（验证 detail 真返回）
    async with test_session_factory() as session:
        p = await session.get(CompanionProfile, profile.id)
        p.bio = "10 年护理经验"
        p.service_area = "北京"
        p.service_city = "北京"
        p.certification_type = "护士资格证"
        p.certification_no = "RN20250001"
        p.certification_image_url = "https://blob.example.com/cert/xxx.jpg"  # PR-E2 才 sign
        p.avg_rating = 4.8
        p.total_orders = 42
        await session.commit()

    resp = await client.get(
        f"{BASE}/{profile.id}",
        headers=_headers(),
    )
    assert resp.status_code == 200
    data = resp.json()
    # 5 字段与 list 重叠
    assert data["id"] == str(profile.id)
    assert data["real_name"] == "详情测试陪诊师"
    assert data["id_number"] is None or "*" in data["id_number"]  # masked
    assert data["created_at"] is not None
    # 新增 9 字段
    assert data["bio"] == "10 年护理经验"
    assert data["verification_status"] == "pending"
    assert data["certified_at"] is None  # 未 certify
    assert data["certification_type"] == "护士资格证"
    assert data["certification_no"] == "RN20250001"
    assert data["certification_image_signed_url"] is None  # ⚠️ PR-E1 占位
    assert data["service_area"] == "北京"
    assert data["service_city"] == "北京"
    assert data["avg_rating"] == 4.8
    assert data["total_orders"] == 42
    # 关联用户
    assert data["user_id"] is not None
    assert data["user_phone_masked"] is not None
    assert "*" in data["user_phone_masked"]  # masked


@pytest.mark.asyncio
async def test_get_companion_detail_writes_audit_log(client):
    """每次 detail GET 写 view_companion_detail audit。"""
    profile = await _create_profile(real_name="审计测试")

    resp = await client.get(
        f"{BASE}/{profile.id}",
        headers=_headers(),
    )
    assert resp.status_code == 200

    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(
                AdminAuditLog.target_id == profile.id,
                AdminAuditLog.action == "view_companion_detail",
            )
        )
        log = result.scalar_one()
        assert log.action == "view_companion_detail"
        assert log.target_type == "companion"


@pytest.mark.asyncio
async def test_get_companion_detail_404_for_missing(client):
    """不存在的 companion_id 返 404。"""
    fake_id = uuid.uuid4()
    resp = await client.get(
        f"{BASE}/{fake_id}",
        headers=_headers(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_companion_detail_requires_admin_token(client):
    """缺 admin token 返 401（require_admin dependency）。"""
    profile = await _create_profile()
    resp = await client.get(
        f"{BASE}/{profile.id}",
        headers={},  # 无 token
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_get_companion_detail_cert_signed_url_is_none_in_pr_e1(client):
    """PR-E1 acceptance 显式降级：cert_image_signed_url 必须返 None
    （即使 DB cert_image_url 已存值），PR-E2 才补 signed URL service。"""
    profile = await _create_profile()

    async with test_session_factory() as session:
        p = await session.get(CompanionProfile, profile.id)
        p.certification_image_url = "https://public.example.com/cert.jpg"  # 模拟已存 public URL
        await session.commit()

    resp = await client.get(
        f"{BASE}/{profile.id}",
        headers=_headers(),
    )
    assert resp.status_code == 200
    # PR-E1 占位：即使 DB 有 cert_image_url，detail 也不返
    assert resp.json()["certification_image_signed_url"] is None
