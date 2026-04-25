"""E2E: full patient journey.

Patient registers via OTP -> browses companions -> creates order ->
pays (mock provider, instant success) -> chats -> companion completes
-> patient submits review.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.e2e


async def _seed_verified_companion(
    e2e_client, login_via_otp, companion_phone, admin_headers
):
    """Register a companion + apply + admin approve. Returns (headers, profile_id)."""
    access, _, _ = await login_via_otp(companion_phone)
    headers = {"Authorization": f"Bearer {access}"}

    r = await e2e_client.post(
        "/api/v1/companions/apply",
        headers=headers,
        json={
            "real_name": "测试陪诊员",
            "id_number": "110101199001011234",
            "service_types": "full_accompany,half_accompany",
            "service_city": "北京",
            "service_area": "海淀,朝阳",
            "bio": "E2E 测试陪诊师",
        },
    )
    assert r.status_code == 201, r.text
    profile_id = r.json()["id"]

    r = await e2e_client.post(
        f"/api/v1/admin/companions/{profile_id}/approve", headers=admin_headers
    )
    assert r.status_code == 200, r.text
    return headers, profile_id


async def test_patient_full_journey(
    e2e_client,
    login_via_otp,
    seed_hospital_e2e,
    patient_phone,
    companion_phone,
    admin_headers,
):
    # 1. Background actor: a verified companion.
    companion_headers, profile_id = await _seed_verified_companion(
        e2e_client, login_via_otp, companion_phone, admin_headers
    )

    # 2. Patient: OTP register/login.
    p_access, _, p_user = await login_via_otp(patient_phone)
    p_headers = {"Authorization": f"Bearer {p_access}"}
    assert p_user["phone"] == patient_phone

    # 3. Browse companions.
    r = await e2e_client.get("/api/v1/companions?city=北京", headers=p_headers)
    assert r.status_code == 200, r.text
    listing = r.json()
    items = listing if isinstance(listing, list) else listing.get("items", [])
    assert any(c["id"] == profile_id for c in items), items

    # 4. Create order.
    hospital = await seed_hospital_e2e()
    r = await e2e_client.post(
        "/api/v1/orders",
        headers=p_headers,
        json={
            "service_type": "full_accompany",
            "hospital_id": str(hospital.id),
            "appointment_date": "2099-05-01",
            "appointment_time": "09:00",
            "description": "E2E 测试订单",
            "companion_id": profile_id,
        },
    )
    assert r.status_code == 201, r.text
    order = r.json()
    order_id = order["id"]
    assert order["status"] == "created"

    # 5. Pay (mock provider).
    r = await e2e_client.post(f"/api/v1/orders/{order_id}/pay", headers=p_headers)
    assert r.status_code == 200, r.text
    assert r.json().get("mock_success") is True

    # 6. Companion accepts.
    r = await e2e_client.post(
        f"/api/v1/orders/{order_id}/accept", headers=companion_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"

    # 7. Chat round-trip.
    r = await e2e_client.post(
        f"/api/v1/chats/{order_id}/messages",
        headers=p_headers,
        json={"content": "你好，我已下单", "type": "text"},
    )
    assert r.status_code == 201, r.text
    r = await e2e_client.post(
        f"/api/v1/chats/{order_id}/messages",
        headers=companion_headers,
        json={"content": "好的，准时到达", "type": "text"},
    )
    assert r.status_code == 201, r.text

    r = await e2e_client.get(
        f"/api/v1/chats/{order_id}/messages", headers=p_headers
    )
    assert r.status_code == 200
    assert r.json()["total"] >= 2

    # 8. Service start -> complete.
    r = await e2e_client.post(
        f"/api/v1/orders/{order_id}/start", headers=companion_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "in_progress"

    r = await e2e_client.post(
        f"/api/v1/orders/{order_id}/complete", headers=companion_headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "completed"

    # 9. Patient reviews.
    r = await e2e_client.post(
        f"/api/v1/orders/{order_id}/review",
        headers=p_headers,
        json={"rating": 5, "content": "服务非常好，准时专业，强烈推荐"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["rating"] == 5

    # Duplicate review must fail.
    r2 = await e2e_client.post(
        f"/api/v1/orders/{order_id}/review",
        headers=p_headers,
        json={"rating": 4, "content": "重复评价应被拒绝，再写一遍试试"},
    )
    assert r2.status_code in (400, 409), r2.text
