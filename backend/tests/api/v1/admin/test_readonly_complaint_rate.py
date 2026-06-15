"""ADR-0053 §AC#4 admin endpoint tests for POST /admin/readonly/complaint-rate."""

from __future__ import annotations

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import create_admin_access_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.services.readonly_complaint_rate_store import (
    reset_default_store_for_tests,
)
from tests.conftest import test_session_factory as _session_factory

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _reset_store_per_test() -> None:
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


async def _seed_admin(username: str = "pm-readonly") -> AdminUser:
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


async def test_post_complaint_rate_records_sample_and_writes_audit(
    client: AsyncClient,
) -> None:
    admin = await _seed_admin("pm-rate-1")
    token = create_admin_access_token(admin)

    resp = await client.post(
        "/api/v1/admin/readonly/complaint-rate",
        headers={"Authorization": f"Bearer {token}"},
        json={"rate": 0.05, "note": "周度抽查"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recorded"] is True
    assert body["rate"] == 0.05
    # rolling avg of single sample = the rate itself
    assert body["rolling_average_7d"] is not None
    assert abs(body["rolling_average_7d"] - 0.05) < 1e-9

    # AdminAuditLog row written in same transaction
    async with _session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_type == "readonly_complaint_rate_sample"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        audit = rows[0]
        assert audit.action == "record"
        assert audit.operator == str(admin.id)
        assert "rate=0.0500%" in audit.reason
        assert "note=周度抽查" in audit.reason


async def test_post_complaint_rate_validates_rate_range(
    client: AsyncClient,
) -> None:
    admin = await _seed_admin("pm-rate-2")
    token = create_admin_access_token(admin)

    # rate negative → 422
    resp = await client.post(
        "/api/v1/admin/readonly/complaint-rate",
        headers={"Authorization": f"Bearer {token}"},
        json={"rate": -0.1},
    )
    assert resp.status_code == 422

    # rate >100 → 422
    resp = await client.post(
        "/api/v1/admin/readonly/complaint-rate",
        headers={"Authorization": f"Bearer {token}"},
        json={"rate": 150.0},
    )
    assert resp.status_code == 422


async def test_post_complaint_rate_requires_admin_auth(
    client: AsyncClient,
) -> None:
    resp = await client.post(
        "/api/v1/admin/readonly/complaint-rate",
        json={"rate": 0.05},
    )
    # 401 or 403 expected (admin auth required)
    assert resp.status_code in (401, 403)


async def test_post_complaint_rate_omitting_note_still_records(
    client: AsyncClient,
) -> None:
    admin = await _seed_admin("pm-rate-3")
    token = create_admin_access_token(admin)

    resp = await client.post(
        "/api/v1/admin/readonly/complaint-rate",
        headers={"Authorization": f"Bearer {token}"},
        json={"rate": 0.012},  # no note
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["recorded"] is True

    # audit row exists, no note in reason
    async with _session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_type == "readonly_complaint_rate_sample",
                        AdminAuditLog.operator == str(admin.id),
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert "rate=0.0120%" in rows[0].reason
        assert "note=" not in rows[0].reason
