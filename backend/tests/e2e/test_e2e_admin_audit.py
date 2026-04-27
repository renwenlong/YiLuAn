"""E2E: admin audit flows.

After B4, all ``/admin/**`` endpoints share a single auth: the
``X-Admin-Token`` header (token-based admin). JWT/role-based admin auth
is deferred to v2 (see ``docs/admin-mvp-scope.md``).
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


async def test_admin_companion_approve_reject_flow(
    e2e_client,
    login_via_otp,
    companion_phone,
    admin_headers,
):
    # Companion applies.
    c_access, _, _ = await login_via_otp(companion_phone, role="companion")
    c_headers = {"Authorization": f"Bearer {c_access}"}
    r = await e2e_client.post(
        "/api/v1/companions/apply",
        headers=c_headers,
        json={
            "real_name": "审核测试",
            "service_types": "full_accompany",
            "service_city": "北京",
        },
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]

    # Listed in pending.
    r = await e2e_client.get("/api/v1/admin/companions/", headers=admin_headers)
    assert r.status_code == 200
    assert profile_id in [p["id"] for p in r.json()["items"]]

    # Approve.
    r = await e2e_client.post(
        f"/api/v1/admin/companions/{profile_id}/approve", headers=admin_headers
    )
    assert r.status_code == 200

    # No longer in pending list.
    r = await e2e_client.get("/api/v1/admin/companions/", headers=admin_headers)
    assert profile_id not in [p["id"] for p in r.json()["items"]]


async def test_admin_endpoint_rejects_missing_token(e2e_client):
    r = await e2e_client.get("/api/v1/admin/companions/")
    assert r.status_code in (401, 403, 422)


async def test_admin_endpoint_rejects_wrong_token(e2e_client):
    r = await e2e_client.get(
        "/api/v1/admin/companions/", headers={"X-Admin-Token": "wrong"}
    )
    assert r.status_code == 401


async def test_admin_orders_requires_admin_token(
    e2e_client, admin_headers
):
    """After B4, /admin/orders uses the same X-Admin-Token guard."""
    # Missing token -> 422 (FastAPI required-header validation).
    r = await e2e_client.get("/api/v1/admin/orders")
    assert r.status_code in (401, 422)

    # Wrong token -> 401.
    r = await e2e_client.get(
        "/api/v1/admin/orders", headers={"X-Admin-Token": "wrong"}
    )
    assert r.status_code == 401

    # Correct token -> 200.
    r = await e2e_client.get("/api/v1/admin/orders", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "items" in body and "total" in body


async def test_admin_disable_blocks_user_access(
    e2e_client,
    login_via_otp,
    patient_phone,
    admin_headers,
):
    """Closed-loop check that ``POST /admin/users/{id}/disable`` actually
    blocks the affected user from authenticated endpoints, and ``/enable``
    restores access. Audit log entries for both transitions must exist.
    """
    # 1. Patient registers and verifies the live token.
    p_access, _, p_user = await login_via_otp(patient_phone, role="patient")
    p_headers = {"Authorization": f"Bearer {p_access}"}
    user_id = p_user["id"]

    r = await e2e_client.get("/api/v1/users/me", headers=p_headers)
    assert r.status_code == 200, r.text

    # 2. Admin disables the user with a reason.
    r = await e2e_client.post(
        f"/api/v1/admin/users/{user_id}/disable",
        headers=admin_headers,
        json={"reason": "e2e test: confirm disable blocks access"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is False

    # 3. Existing access token must now be rejected (auth dependency checks is_active).
    r = await e2e_client.get("/api/v1/users/me", headers=p_headers)
    assert r.status_code in (401, 403), (
        f"disabled user should not call /me; got {r.status_code} {r.text}"
    )

    # 4. Re-login attempt must also fail (verify-otp checks is_active).
    r = await e2e_client.post(
        "/api/v1/auth/send-otp", json={"phone": patient_phone}
    )
    # send-otp may succeed, hit rate limit (400), or 403; we don't gate on this step.
    assert r.status_code in (200, 400, 403)
    r = await e2e_client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": patient_phone, "code": "000000"},
    )
    assert r.status_code in (401, 403), (
        f"disabled user should not be able to verify-otp; got {r.status_code} {r.text}"
    )

    # 5. Admin re-enables.
    r = await e2e_client.post(
        f"/api/v1/admin/users/{user_id}/enable",
        headers=admin_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["is_active"] is True

    # 6. Login works again.
    new_access, _, _ = await login_via_otp(patient_phone, role="patient")
    new_headers = {"Authorization": f"Bearer {new_access}"}
    r = await e2e_client.get("/api/v1/users/me", headers=new_headers)
    assert r.status_code == 200, r.text

    # 7. Audit trail: both disable + enable rows exist for this user.
    from uuid import UUID

    from sqlalchemy import select

    from app.models.admin_audit_log import AdminAuditLog
    from tests.e2e.conftest import test_session_factory  # type: ignore[attr-defined]

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_type == "user",
                    AdminAuditLog.target_id == UUID(str(user_id)),
                )
            )
        ).scalars().all()
    actions = {r.action for r in rows}
    assert "disable" in actions, f"missing disable audit: {actions}"
    assert "enable" in actions, f"missing enable audit: {actions}"

