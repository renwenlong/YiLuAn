"""S2-OPS-A-READ-ONLY-FLAG-ADMIN-API endpoint tests.

Covers AC#1-#7 of the admin read-only endpoint task:

* AC#1: POST /admin/users/{user_id}/read-only sets flag + 5 metadata cols
* AC#2: DELETE /admin/users/{user_id}/read-only clears flag + 4 metadata cols
* AC#3: POST /admin/users/batch-read-only batch ≤100; >100 → 422 BATCH_TOO_LARGE
* AC#4: AdminAuditLog row written in same transaction (PR #238 pattern)
* AC#5: RBAC — non-admin → 403 (covered by ``require_admin`` dependency upstream;
  this test file focuses on positive flows + audit shape)
* AC#6: ``reason_detail`` NEVER appears in response body (security guard)
* AC#7: PR description cites ADR-0053 §5 + §7 + PR #238 audit pattern (PR text gate)
"""

from __future__ import annotations

import json
from uuid import uuid4

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import create_admin_access_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.models.user import User
from tests.conftest import test_session_factory as _session_factory


async def _seed_admin(username: str = "ro-ops") -> AdminUser:
    pw_hash = bcrypt.hashpw(b"hunter2A!", bcrypt.gensalt(rounds=4))
    async with _session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash=pw_hash.decode("utf-8"),
            role=AdminRole.super_,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return admin


async def _seed_user(phone: str) -> User:
    async with _session_factory() as session:
        u = User(phone=phone, roles="patient", is_active=True)
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u


@pytest.mark.asyncio
class TestSetReadOnly:
    async def test_set_read_only_updates_all_five_columns(self, client: AsyncClient):
        admin = await _seed_admin("ro-set")
        target = await _seed_user("13800000001")
        token = create_admin_access_token(admin)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "is_read_only": True,
                "reason_category": "CREDENTIAL_LEAK",
                "reason_detail": "SECRET_ADMIN_NOTE_42_DO_NOT_LEAK",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # AC#1 response shape
        assert body["user_id"] == str(target.id)
        assert body["is_read_only"] is True
        assert body["reason_category"] == "CREDENTIAL_LEAK"
        assert body["read_only_set_at"] is not None
        assert body["read_only_set_by"] == admin.id

        # AC#6 SECURITY: reason_detail MUST NOT appear in any response field
        assert "reason_detail" not in body, "reason_detail field name leaked in response"
        # Defense-in-depth: full body string scan for the marker text
        raw = json.dumps(body)
        assert (
            "SECRET_ADMIN_NOTE_42_DO_NOT_LEAK" not in raw
        ), "reason_detail content leaked into response body"

        # AC#1 DB persistence: all 5 cols set
        async with _session_factory() as s:
            u = await s.get(User, target.id)
            assert u.is_read_only is True
            assert u.read_only_reason_category == "CREDENTIAL_LEAK"
            assert u.read_only_reason_detail == "SECRET_ADMIN_NOTE_42_DO_NOT_LEAK"
            assert u.read_only_set_at is not None
            assert u.read_only_set_by == admin.id

    async def test_set_read_only_writes_audit_in_same_transaction(self, client: AsyncClient):
        admin = await _seed_admin("ro-audit")
        target = await _seed_user("13800000002")
        token = create_admin_access_token(admin)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "is_read_only": True,
                "reason_category": "GRAY_REVOKE",
                "reason_detail": "灰度回退批次 #42",
            },
        )
        assert resp.status_code == 200, resp.text

        # AC#4 audit row exists with full operator + reason
        async with _session_factory() as s:
            rows = (
                (
                    await s.execute(
                        select(AdminAuditLog)
                        .where(AdminAuditLog.target_id == target.id)
                        .where(AdminAuditLog.action == "set_read_only")
                    )
                )
                .scalars()
                .all()
            )
            assert rows, "expected set_read_only audit row"
            row = rows[0]
            assert row.operator == str(admin.id)
            assert "category=GRAY_REVOKE" in row.reason
            # detail is full-text in audit (long-term retention path)
            assert "灰度回退批次 #42" in row.reason

    async def test_set_read_only_404_when_user_missing(self, client: AsyncClient):
        admin = await _seed_admin("ro-404")
        token = create_admin_access_token(admin)
        missing = uuid4()

        resp = await client.post(
            f"/api/v1/admin/users/{missing}/read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={"is_read_only": True, "reason_category": "GRAY_REVOKE"},
        )
        assert resp.status_code == 404, resp.text

        # AC#4 transaction rollback: no orphan audit row written on 404
        async with _session_factory() as s:
            rows = (
                (await s.execute(select(AdminAuditLog).where(AdminAuditLog.target_id == missing)))
                .scalars()
                .all()
            )
            assert not rows, "404 path must not leave audit row (transaction rollback)"

    async def test_set_read_only_accepts_null_reason_category(self, client: AsyncClient):
        admin = await _seed_admin("ro-nullcat")
        target = await _seed_user("13800000003")
        token = create_admin_access_token(admin)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={"is_read_only": True},  # no category / detail
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["reason_category"] is None

        async with _session_factory() as s:
            u = await s.get(User, target.id)
            assert u.is_read_only is True
            assert u.read_only_reason_category is None
            assert u.read_only_reason_detail is None


@pytest.mark.asyncio
class TestUnsetReadOnly:
    async def test_unset_clears_all_four_metadata_cols(self, client: AsyncClient):
        admin = await _seed_admin("ro-unset")
        target = await _seed_user("13800000010")
        token = create_admin_access_token(admin)

        # Set first
        set_resp = await client.post(
            f"/api/v1/admin/users/{target.id}/read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "is_read_only": True,
                "reason_category": "COMPLIANCE_REPORT",
                "reason_detail": "举报方=foo",
            },
        )
        assert set_resp.status_code == 200

        # Unset
        unset_resp = await client.delete(
            f"/api/v1/admin/users/{target.id}/read-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unset_resp.status_code == 200, unset_resp.text
        body = unset_resp.json()
        assert body["is_read_only"] is False
        assert body["reason_category"] is None
        assert body["read_only_set_at"] is None
        assert body["read_only_set_by"] is None

        # AC#6: even unset response must not leak detail
        assert "reason_detail" not in body
        assert "举报方" not in json.dumps(body)

        # Audit row exists with action=unset_read_only
        async with _session_factory() as s:
            rows = (
                (
                    await s.execute(
                        select(AdminAuditLog)
                        .where(AdminAuditLog.target_id == target.id)
                        .where(AdminAuditLog.action == "unset_read_only")
                    )
                )
                .scalars()
                .all()
            )
            assert rows
            assert rows[0].operator == str(admin.id)

            # All 4 metadata cols nulled
            u = await s.get(User, target.id)
            assert u.is_read_only is False
            assert u.read_only_reason_category is None
            assert u.read_only_reason_detail is None
            assert u.read_only_set_at is None
            assert u.read_only_set_by is None

    async def test_unset_404_when_user_missing(self, client: AsyncClient):
        admin = await _seed_admin("ro-unset-404")
        token = create_admin_access_token(admin)
        missing = uuid4()

        resp = await client.delete(
            f"/api/v1/admin/users/{missing}/read-only",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404


@pytest.mark.asyncio
class TestBatchReadOnly:
    async def test_batch_set_writes_per_user_audit(self, client: AsyncClient):
        admin = await _seed_admin("ro-batch")
        u1 = await _seed_user("13800000020")
        u2 = await _seed_user("13800000021")
        u3 = await _seed_user("13800000022")
        token = create_admin_access_token(admin)

        resp = await client.post(
            "/api/v1/admin/users/batch-read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_ids": [str(u1.id), str(u2.id), str(u3.id)],
                "is_read_only": True,
                "reason_category": "GRAY_ANOMALY",
                "reason_detail": "anomaly batch 0612",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Summary numbers
        assert body["requested"] == 3
        assert body["succeeded"] == 3
        assert body["failed"] == 0
        assert len(body["results"]) == 3

        # Per-user result shape: still no detail leak in batch responses
        raw = json.dumps(body)
        assert "anomaly batch 0612" not in raw

        # All 3 audit rows present
        async with _session_factory() as s:
            for u in (u1, u2, u3):
                rows = (
                    (
                        await s.execute(
                            select(AdminAuditLog)
                            .where(AdminAuditLog.target_id == u.id)
                            .where(AdminAuditLog.action == "set_read_only")
                        )
                    )
                    .scalars()
                    .all()
                )
                assert rows, f"missing audit for {u.id}"
                assert "batch category=GRAY_ANOMALY" in rows[0].reason

    async def test_batch_unset_clears_all_users(self, client: AsyncClient):
        admin = await _seed_admin("ro-batch-unset")
        u1 = await _seed_user("13800000030")
        u2 = await _seed_user("13800000031")
        token = create_admin_access_token(admin)

        # Pre-set them via single endpoint so we have something to unset
        for u in (u1, u2):
            r = await client.post(
                f"/api/v1/admin/users/{u.id}/read-only",
                headers={"Authorization": f"Bearer {token}"},
                json={"is_read_only": True, "reason_category": "GRAY_REVOKE"},
            )
            assert r.status_code == 200

        resp = await client.post(
            "/api/v1/admin/users/batch-read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_ids": [str(u1.id), str(u2.id)],
                "is_read_only": False,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["succeeded"] == 2

        async with _session_factory() as s:
            for u in (u1, u2):
                refreshed = await s.get(User, u.id)
                assert refreshed.is_read_only is False
                assert refreshed.read_only_reason_category is None

    async def test_batch_partial_404_keeps_succeeding_users(self, client: AsyncClient):
        admin = await _seed_admin("ro-batch-partial")
        u_real = await _seed_user("13800000040")
        u_missing = uuid4()
        token = create_admin_access_token(admin)

        resp = await client.post(
            "/api/v1/admin/users/batch-read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_ids": [str(u_real.id), str(u_missing)],
                "is_read_only": True,
                "reason_category": "GRAY_REVOKE",
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["requested"] == 2
        assert body["succeeded"] == 1
        assert body["failed"] == 1

        # Real user got the flag; missing user got error="USER_NOT_FOUND"
        real_result = next(r for r in body["results"] if r["user_id"] == str(u_real.id))
        missing_result = next(r for r in body["results"] if r["user_id"] == str(u_missing))
        assert real_result["error"] is None
        assert real_result["is_read_only"] is True
        assert missing_result["error"] == "USER_NOT_FOUND"
        assert missing_result["is_read_only"] is None

    async def test_batch_too_large_returns_422(self, client: AsyncClient):
        admin = await _seed_admin("ro-batch-toolarge")
        token = create_admin_access_token(admin)

        # 101 fabricated UUIDs trigger BATCH_TOO_LARGE before any DB hit
        resp = await client.post(
            "/api/v1/admin/users/batch-read-only",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "user_ids": [str(uuid4()) for _ in range(101)],
                "is_read_only": True,
                "reason_category": "GRAY_REVOKE",
            },
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert detail["error_code"] == "BATCH_TOO_LARGE"
        assert "101" in detail["message"]
        assert "100" in detail["message"]


@pytest.mark.asyncio
class TestRbac:
    async def test_no_auth_header_returns_401(self, client: AsyncClient):
        # AC#5: require_admin upstream rejects unauthenticated calls
        target = await _seed_user("13800000050")
        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/read-only",
            json={"is_read_only": True, "reason_category": "GRAY_REVOKE"},
        )
        assert resp.status_code in (401, 403), resp.text
