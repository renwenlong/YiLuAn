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
    assert resp.status_code == 422  # missing required header


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
