"""Admin v2 tests (B6 / ADR-0034).

Covers:

* login success / wrong password / disabled account
* JWT decoding: type-mismatch, expired
* dual-track auth: JWT principal vs legacy X-Admin-Token sentinel
* audit log operator: real admin_user.id vs 'admin-token'
* require_admin precedence (Authorization wins over X-Admin-Token)
"""

from __future__ import annotations

from datetime import timedelta

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import (
    LEGACY_ADMIN_TOKEN_SENTINEL,
    create_admin_access_token,
)
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser

from tests.conftest import test_session_factory


async def _seed_admin(
    *,
    username: str = "neo",
    password: str = "Matrix@2026!",
    role: AdminRole = AdminRole.super_,
    is_active: bool = True,
) -> AdminUser:
    pw_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=4))
    async with test_session_factory() as session:
        user = AdminUser(
            username=username,
            password_hash=pw_hash.decode("utf-8"),
            role=role,
            is_active=is_active,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
class TestAdminLogin:
    async def test_login_success(self, client: AsyncClient):
        await _seed_admin(username="ops1", password="hunter2A!")
        resp = await client.post(
            "/api/v1/admin/login",
            json={"username": "ops1", "password": "hunter2A!"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["token_type"] == "bearer"
        assert body["role"] == "super"
        assert body["username"] == "ops1"
        assert body["expires_in"] == 8 * 3600
        assert isinstance(body["access_token"], str) and len(body["access_token"]) > 20

        # last_login_at gets stamped.
        async with test_session_factory() as session:
            row = (
                await session.execute(
                    select(AdminUser).where(AdminUser.username == "ops1")
                )
            ).scalar_one()
            assert row.last_login_at is not None

    async def test_login_wrong_password(self, client: AsyncClient):
        await _seed_admin(username="ops2", password="correct!")
        resp = await client.post(
            "/api/v1/admin/login",
            json={"username": "ops2", "password": "wrong!"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_user_is_401(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/admin/login",
            json={"username": "nobody", "password": "whatever"},
        )
        assert resp.status_code == 401

    async def test_login_disabled_account(self, client: AsyncClient):
        await _seed_admin(
            username="ops3",
            password="goodpass!",
            is_active=False,
        )
        resp = await client.post(
            "/api/v1/admin/login",
            json={"username": "ops3", "password": "goodpass!"},
        )
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestAdminJwtDualTrack:
    async def test_jwt_grants_access(self, client: AsyncClient):
        admin = await _seed_admin(username="finance1", role=AdminRole.finance)
        token = create_admin_access_token(admin)
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text

    async def test_jwt_audit_records_real_operator_id(
        self, client: AsyncClient
    ):
        admin = await _seed_admin(username="ops-audit")
        token = create_admin_access_token(admin)
        # disable a freshly-seeded user so we trigger an audit row
        async with test_session_factory() as session:
            from app.models.user import User

            target = User(phone="13700137001", roles="patient", is_active=True)
            session.add(target)
            await session.commit()
            await session.refresh(target)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/disable",
            headers={"Authorization": f"Bearer {token}"},
            json={"reason": "audit-operator-test"},
        )
        assert resp.status_code == 200, resp.text

        async with test_session_factory() as session:
            rows = (
                await session.execute(
                    select(AdminAuditLog)
                    .where(AdminAuditLog.target_id == target.id)
                    .where(AdminAuditLog.action == "disable")
                )
            ).scalars().all()
            assert rows, "expected disable audit row"
            # operator must be the real admin id (string), NOT the legacy sentinel.
            assert all(r.operator == str(admin.id) for r in rows)
            assert all(r.operator != LEGACY_ADMIN_TOKEN_SENTINEL for r in rows)

    async def test_legacy_token_audit_keeps_sentinel(
        self, client: AsyncClient
    ):
        async with test_session_factory() as session:
            from app.models.user import User

            target = User(phone="13700137002", roles="patient", is_active=True)
            session.add(target)
            await session.commit()
            await session.refresh(target)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/disable",
            headers={"X-Admin-Token": "dev-admin-token"},
            json={"reason": "legacy-audit"},
        )
        assert resp.status_code == 200, resp.text

        async with test_session_factory() as session:
            rows = (
                await session.execute(
                    select(AdminAuditLog)
                    .where(AdminAuditLog.target_id == target.id)
                    .where(AdminAuditLog.action == "disable")
                )
            ).scalars().all()
            assert rows
            assert all(r.operator == LEGACY_ADMIN_TOKEN_SENTINEL for r in rows)

    async def test_jwt_takes_precedence_over_x_admin_token(
        self, client: AsyncClient
    ):
        admin = await _seed_admin(username="precedence-test")
        token = create_admin_access_token(admin)
        async with test_session_factory() as session:
            from app.models.user import User

            target = User(phone="13700137003", roles="patient", is_active=True)
            session.add(target)
            await session.commit()
            await session.refresh(target)

        resp = await client.post(
            f"/api/v1/admin/users/{target.id}/disable",
            headers={
                "Authorization": f"Bearer {token}",
                # Bogus legacy token: must be ignored because JWT wins.
                "X-Admin-Token": "definitely-wrong",
            },
            json={"reason": "precedence"},
        )
        assert resp.status_code == 200, resp.text

        async with test_session_factory() as session:
            rows = (
                await session.execute(
                    select(AdminAuditLog)
                    .where(AdminAuditLog.target_id == target.id)
                    .where(AdminAuditLog.action == "disable")
                )
            ).scalars().all()
            assert rows
            assert all(r.operator == str(admin.id) for r in rows)

    async def test_jwt_disabled_admin_is_rejected(self, client: AsyncClient):
        admin = await _seed_admin(username="ghost", is_active=True)
        token = create_admin_access_token(admin)
        # disable after token issued
        async with test_session_factory() as session:
            row = (
                await session.execute(
                    select(AdminUser).where(AdminUser.id == admin.id)
                )
            ).scalar_one()
            row.is_active = False
            await session.commit()

        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_jwt_expired_is_rejected(self, client: AsyncClient):
        admin = await _seed_admin(username="time-traveler")
        token = create_admin_access_token(
            admin, expires_in=timedelta(seconds=-1)
        )
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401

    async def test_user_token_is_rejected_on_admin_endpoint(
        self, client: AsyncClient
    ):
        # User-side access tokens (type='access') must NOT cross over.
        from app.core.security import create_access_token

        bad = create_access_token({"sub": "00000000-0000-0000-0000-000000000001"})
        resp = await client.get(
            "/api/v1/admin/users",
            headers={"Authorization": f"Bearer {bad}"},
        )
        assert resp.status_code == 401

    async def test_no_auth_at_all_is_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/admin/orders")
        assert resp.status_code == 401
