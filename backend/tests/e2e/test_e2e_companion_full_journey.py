"""E2E: full companion journey.

Companion registers via OTP -> applies for verification -> admin
approves (status pending -> verified) -> accepts a paid order ->
service start -> service complete -> stats reflect the order.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


async def test_companion_full_journey(
    e2e_client,
    login_via_otp,
    seed_hospital_e2e,
    patient_phone,
    companion_phone,
    admin_headers,
):
    # 1. Companion: OTP register/login.
    c_access, _, c_user = await login_via_otp(companion_phone)
    c_headers = {"Authorization": f"Bearer {c_access}"}
    assert c_user["phone"] == companion_phone
    assert c_user["role"] is None  # No role yet.

    # 2. Apply for verification.
    r = await e2e_client.post(
        "/api/v1/companions/apply",
        headers=c_headers,
        json={
            "real_name": "陪诊师小李",
            "id_number": "110101199001011234",
            "service_types": "full_accompany,half_accompany,errand",
            "service_city": "北京",
            "bio": "5年陪诊经验",
        },
    )
    assert r.status_code == 201, r.text
    profile = r.json()
    profile_id = profile["id"]
    assert profile["verification_status"] == "pending"

    # 3. Admin: pending list contains this profile, then approve.
    r = await e2e_client.get("/api/v1/admin/companions/", headers=admin_headers)
    assert r.status_code == 200, r.text
    pending_ids = [item["id"] for item in r.json()["items"]]
    assert profile_id in pending_ids

    r = await e2e_client.post(
        f"/api/v1/admin/companions/{profile_id}/approve", headers=admin_headers
    )
    assert r.status_code == 200, r.text

    r = await e2e_client.get("/api/v1/companions/me", headers=c_headers)
    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "verified"

    # 4. Patient creates + pays for an order targeting this companion.
    p_access, _, _ = await login_via_otp(patient_phone)
    p_headers = {"Authorization": f"Bearer {p_access}"}

    hospital = await seed_hospital_e2e()
    r = await e2e_client.post(
        "/api/v1/orders",
        headers=p_headers,
        json={
            "service_type": "half_accompany",
            "hospital_id": str(hospital.id),
            "appointment_date": "2099-06-01",
            "appointment_time": "10:00",
            "companion_id": profile_id,
        },
    )
    assert r.status_code == 201, r.text
    order_id = r.json()["id"]

    r = await e2e_client.post(f"/api/v1/orders/{order_id}/pay", headers=p_headers)
    assert r.status_code == 200, r.text

    # 5. Companion: accept -> start -> complete.
    r = await e2e_client.post(f"/api/v1/orders/{order_id}/accept", headers=c_headers)
    assert r.status_code == 200, r.text

    r = await e2e_client.post(f"/api/v1/orders/{order_id}/start", headers=c_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = await e2e_client.post(f"/api/v1/orders/{order_id}/complete", headers=c_headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    # 6. Companion stats reflect the completed order.
    # `total_orders` only ticks on review submission; earnings include
    # all completed/reviewed orders, so we assert on earnings here and
    # exercise total_orders in the patient-journey suite (which posts a
    # review).
    r = await e2e_client.get("/api/v1/companions/me/stats", headers=c_headers)
    assert r.status_code == 200, r.text
    stats = r.json()
    assert stats["open_orders"] == 0
    assert stats["total_earnings"] >= 199.0


async def test_companion_apply_rejected(
    e2e_client,
    login_via_otp,
    companion_phone,
    admin_headers,
):
    c_access, _, _ = await login_via_otp(companion_phone)
    c_headers = {"Authorization": f"Bearer {c_access}"}

    r = await e2e_client.post(
        "/api/v1/companions/apply",
        headers=c_headers,
        json={
            "real_name": "拒审测试",
            "service_types": "full_accompany",
            "service_city": "北京",
        },
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]

    r = await e2e_client.post(
        f"/api/v1/admin/companions/{profile_id}/reject",
        headers=admin_headers,
        json={"reason": "证件信息不完整"},
    )
    assert r.status_code == 200, r.text

    r = await e2e_client.get("/api/v1/companions/me", headers=c_headers)
    assert r.status_code == 200, r.text
    assert r.json()["verification_status"] == "rejected"
