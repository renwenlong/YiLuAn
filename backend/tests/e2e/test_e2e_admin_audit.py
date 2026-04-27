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

