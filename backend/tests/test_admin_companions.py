"""
Tests for admin companions audit endpoints (B1).

Covers: auth (token), list, approve, reject, edge cases.
"""

import time
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
        # S3-DEV-003-PRECHECK-BACKEND c1 — approve must stamp
        # verification_completed_at as part of the same transaction.
        # OrderPrecheckSummaryView.companion_cert_status surfaces this
        # as `companion_cert_verified_at` (positive-list field).
        assert updated.verification_completed_at is not None

    # Verify audit log created
    async with test_session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog).where(AdminAuditLog.target_id == profile.id)
        )
        logs = result.scalars().all()
        assert len(logs) == 1
        assert logs[0].action == "approve"


@pytest.mark.asyncio
async def test_approve_sets_verification_completed_at_to_recent_utc(client):
    """Explicit sentinel for the verification_completed_at stamp.

    S3-DEV-003-PRECHECK-BACKEND c1 — verifies the field semantic:

    * NULL before approve
    * NOT NULL after approve, set to ``datetime.now(timezone.utc)``
      at the moment ``verification_status`` flips to ``verified``
    * timestamp must be tz-aware (DateTime(timezone=True)) and within
      a small window of "now" (sanity check the stamp is fresh, not
      a stale leftover from elsewhere)

    Distinct from ``certified_at`` (cert issuance) — do NOT replace
    this with a ``certified_at`` check.
    """
    from datetime import datetime, timedelta, timezone

    profile = await _create_profile()
    # Sanity: fresh pending profile has no verify timestamp yet.
    async with test_session_factory() as session:
        pre = await session.get(CompanionProfile, profile.id)
        assert pre.verification_completed_at is None

    before = datetime.now(timezone.utc)
    resp = await client.post(f"{BASE}/{profile.id}/approve", headers=_headers())
    assert resp.status_code == 200
    after = datetime.now(timezone.utc)

    async with test_session_factory() as session:
        updated = await session.get(CompanionProfile, profile.id)
        stamp = updated.verification_completed_at
        assert stamp is not None, "approve_companion must set verification_completed_at"
        # Note: tz-awareness varies by backend (PG preserves with
        # DateTime(timezone=True); SQLite in-memory tests drop tz).
        # The Smoke Tests CI job runs against real Postgres and proves
        # tz preservation end-to-end; here we just check freshness.
        # Normalize both to naive UTC for freshness compare so the test
        # passes on either backend.
        before_naive = before.replace(tzinfo=None)
        after_naive = after.replace(tzinfo=None)
        stamp_naive = stamp.replace(tzinfo=None) if stamp.tzinfo else stamp
        assert (
            before_naive - timedelta(seconds=5) <= stamp_naive <= after_naive + timedelta(seconds=5)
        ), (
            f"verification_completed_at {stamp} not within approve call window "
            f"[{before}, {after}]"
        )
        # Reject case sanity: this happens to be approve, but make sure
        # we didn't accidentally write a non-verified timestamp by also
        # checking the status is verified.
        assert updated.verification_status == VerificationStatus.verified


@pytest.mark.asyncio
async def test_reject_does_not_set_verification_completed_at(client):
    """Reject path MUST NOT touch verification_completed_at.

    S3-DEV-003-PRECHECK-BACKEND c1 — the field semantic is
    "the moment verification completed successfully". A rejected
    profile never completed verification, so the field stays NULL.
    Catches accidental code reuse ("both approve and reject stamp
    the timestamp") which would silently leak to OrderPrecheckSummaryView.
    """
    profile = await _create_profile()
    resp = await client.post(
        f"{BASE}/{profile.id}/reject",
        headers=_headers(),
        json={"reason": "test reject reason"},
    )
    assert resp.status_code == 200

    async with test_session_factory() as session:
        updated = await session.get(CompanionProfile, profile.id)
        assert updated.verification_status == VerificationStatus.rejected
        assert updated.verification_completed_at is None, (
            "reject must NOT set verification_completed_at — "
            "field semantic is 'verify completed', not 'admin decided'"
        )


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
    # legacy external URL remains hidden until Phase B migration
    assert data["certification_image_signed_url"] is None
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
async def test_get_companion_detail_hides_legacy_external_cert_url(client):
    """PR-E2 Phase A only signs local cert-image:// objects; legacy external URLs stay hidden."""
    profile = await _create_profile()

    async with test_session_factory() as session:
        p = await session.get(CompanionProfile, profile.id)
        p.certification_image_url = "https://public.example.com/cert.jpg"  # Phase B migrates these
        await session.commit()

    resp = await client.get(
        f"{BASE}/{profile.id}",
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["certification_image_signed_url"] is None


@pytest.mark.asyncio
async def test_upload_certification_image_and_detail_returns_signed_url(
    client,
    tmp_path,
    monkeypatch,
):
    from app.services import certification_image as cert_image

    monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
    profile = await _create_profile()

    upload = await client.post(
        f"{BASE}/certification-images",
        headers=_headers(),
        files={"file": ("cert.png", b"fake-png-bytes", "image/png")},
    )
    assert upload.status_code == 200
    body = upload.json()
    assert body["certification_image_url"].startswith("cert-image://")
    assert body["certification_image_signed_url"].startswith(
        "/api/v1/admin/companions/certification-images/"
    )

    async with test_session_factory() as session:
        p = await session.get(CompanionProfile, profile.id)
        p.certification_image_url = body["certification_image_url"]
        await session.commit()

    detail = await client.get(f"{BASE}/{profile.id}", headers=_headers())
    assert detail.status_code == 200
    signed_url = detail.json()["certification_image_signed_url"]
    assert signed_url is not None
    assert "expires=" in signed_url and "sig=" in signed_url

    image = await client.get(signed_url, headers=_headers())
    assert image.status_code == 200
    assert image.content == b"fake-png-bytes"
    assert image.headers["content-type"] == "image/png"

    # 双闸：同一 signed URL 缺 admin token 拒 401/403
    no_token = await client.get(signed_url)
    assert no_token.status_code in (401, 403)

    # 双闸：HMAC 过有错 admin token 仍拒
    bad_admin = await client.get(signed_url, headers=_headers("bad-token"))
    assert bad_admin.status_code in (401, 403)


@pytest.mark.asyncio
async def test_upload_certification_image_rejects_invalid_type(client, tmp_path, monkeypatch):
    from app.services import certification_image as cert_image

    monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
    resp = await client.post(
        f"{BASE}/certification-images",
        headers=_headers(),
        files={"file": ("cert.txt", b"not image", "text/plain")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_certification_image_rejects_too_large(client, tmp_path, monkeypatch):
    from app.services import certification_image as cert_image

    monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
    resp = await client.post(
        f"{BASE}/certification-images",
        headers=_headers(),
        files={"file": ("cert.jpg", b"x" * (5 * 1024 * 1024 + 1), "image/jpeg")},
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_signed_certification_image_rejects_tampered_and_expired(
    client,
    tmp_path,
    monkeypatch,
):
    from app.services import certification_image as cert_image

    monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
    marker = "cert-image://abc123.png"
    (tmp_path / "abc123.png").write_bytes(b"image")
    signed = cert_image.sign_certification_image_url(marker, now=int(time.time()))
    assert signed is not None

    tampered = signed.replace("sig=", "sig=x")
    resp = await client.get(tampered, headers=_headers())
    assert resp.status_code == 403

    expired = cert_image.sign_certification_image_url(marker, now=int(time.time()) - 3600)
    assert expired is not None
    resp = await client.get(expired, headers=_headers())
    assert resp.status_code == 403
