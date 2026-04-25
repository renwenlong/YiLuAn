"""F-01: Companion certification display tests.

Covers:
- New CompanionProfile fields (certification_type/no/image_url/certified_at).
- Admin POST /api/v1/admin/companions/{id}/certify endpoint.
- GET /api/v1/companions/{id} returns the four certification fields.
"""

import uuid
from datetime import datetime, timezone

import pytest

from app.core.security import create_access_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User, UserRole
from sqlalchemy import select

from tests.conftest import test_session_factory

ADMIN_TOKEN = "dev-admin-token"
ADMIN_BASE = "/api/v1/admin/companions"
PUBLIC_BASE = "/api/v1/companions"


def _admin_headers() -> dict:
    return {"X-Admin-Token": ADMIN_TOKEN}


async def _create_companion(real_name: str = "认证测试") -> tuple[CompanionProfile, User]:
    async with test_session_factory() as session:
        user_id = uuid.uuid4()
        phone = f"139{uuid.uuid4().int % 100000000:08d}"
        owner = User(
            id=user_id,
            phone=phone,
            role=UserRole.companion,
            display_name=real_name,
        )
        session.add(owner)
        profile = CompanionProfile(
            user_id=user_id,
            real_name=real_name,
            verification_status=VerificationStatus.verified,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        await session.refresh(owner)
        return profile, owner


def _user_headers(user_id: uuid.UUID) -> dict:
    token = create_access_token({"sub": str(user_id), "role": "companion"})
    return {"Authorization": f"Bearer {token}"}


# ---- Model field defaults ----


@pytest.mark.asyncio
async def test_companion_profile_certification_fields_default_none():
    """New fields default to NULL when not set."""
    profile, _ = await _create_companion("默认值测试")
    async with test_session_factory() as session:
        fresh = await session.get(CompanionProfile, profile.id)
        assert fresh.certification_type is None
        assert fresh.certification_no is None
        assert fresh.certification_image_url is None
        assert fresh.certified_at is None


# ---- Public endpoint returns certification fields ----


@pytest.mark.asyncio
async def test_get_companion_returns_certification_fields(client):
    profile, owner = await _create_companion("公开字段测试")
    # Patch certification directly via DB
    async with test_session_factory() as session:
        db_profile = await session.get(CompanionProfile, profile.id)
        db_profile.certification_type = "护士证"
        db_profile.certification_no = "NO.20231234"
        db_profile.certification_image_url = "https://oss.example.com/cert/abc.jpg"
        db_profile.certified_at = datetime.now(timezone.utc)
        await session.commit()

    resp = await client.get(f"{PUBLIC_BASE}/{profile.id}", headers=_user_headers(owner.id))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["certification_type"] == "护士证"
    assert body["certification_no"] == "NO.20231234"
    assert body["certification_image_url"] == "https://oss.example.com/cert/abc.jpg"
    assert body["certified_at"] is not None


# ---- Admin certify endpoint ----


@pytest.mark.asyncio
async def test_admin_certify_companion_success(client):
    profile, _ = await _create_companion("认证写入")
    payload = {
        "certification_type": "健康管理师",
        "certification_no": "HM-2026-0001",
        "certification_image_url": "https://oss.example.com/cert/hm-001.jpg",
    }
    resp = await client.post(
        f"{ADMIN_BASE}/{profile.id}/certify",
        json=payload,
        headers=_admin_headers(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["certification_type"] == "健康管理师"
    assert body["certification_no"] == "HM-2026-0001"
    assert body["certification_image_url"] == "https://oss.example.com/cert/hm-001.jpg"
    assert body["certified_at"] is not None

    # Audit log written
    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(AdminAuditLog.target_id == profile.id)
        )
        logs = result.scalars().all()
        assert any(log.action == "certify" for log in logs)


@pytest.mark.asyncio
async def test_admin_certify_companion_missing_token_rejected(client):
    profile, _ = await _create_companion("无 token")
    resp = await client.post(
        f"{ADMIN_BASE}/{profile.id}/certify",
        json={
            "certification_type": "护士证",
            "certification_no": "NO.1",
            "certification_image_url": "https://x.com/a.jpg",
        },
    )
    # Missing required header X-Admin-Token => 422
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_certify_companion_not_found(client):
    resp = await client.post(
        f"{ADMIN_BASE}/{uuid.uuid4()}/certify",
        json={
            "certification_type": "护士证",
            "certification_no": "NO.1",
            "certification_image_url": "https://x.com/a.jpg",
        },
        headers=_admin_headers(),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_admin_certify_companion_validation_error(client):
    profile, _ = await _create_companion("校验错误")
    # missing certification_image_url
    resp = await client.post(
        f"{ADMIN_BASE}/{profile.id}/certify",
        json={"certification_type": "护士证", "certification_no": "NO.1"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 422
