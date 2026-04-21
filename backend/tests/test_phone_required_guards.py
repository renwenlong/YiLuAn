"""Phone-required guard tests.

Covers the layered phone-binding precondition introduced for:
- Patient creating an order
- Companion accepting an order
- Companion applying for verification (companion_profile)
- Admin approving (verifying) a companion whose owner has no phone

All paths must return HTTP 400 with ``error_code = PHONE_REQUIRED``
so the frontend dispatchers can drive the bind-phone flow uniformly.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core import error_codes
from app.core.security import create_access_token
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.order import OrderStatus
from app.models.user import UserRole
from tests.conftest import test_session_factory


def _extract_error_code(payload: dict) -> str | None:
    """Detail can be a plain string (legacy) or {error_code, message} dict."""
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail.get("error_code")
    return None


# ---------- Patient creating order ----------


@pytest.mark.asyncio
async def test_create_order_requires_phone(client: AsyncClient, seed_user, seed_hospital):
    """无手机号患者下单 → 400 PHONE_REQUIRED"""
    patient = await seed_user(phone=None, role=UserRole.patient)
    token = create_access_token({"sub": str(patient.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    hospital = await seed_hospital()
    resp = await client.post(
        "/api/v1/orders",
        json={
            "service_type": "full_accompany",
            "hospital_id": str(hospital.id),
            "appointment_date": "2027-05-01",
            "appointment_time": "09:00",
        },
    )
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PHONE_REQUIRED


# ---------- Companion accepting order ----------


@pytest.mark.asyncio
async def test_accept_order_requires_phone(
    client: AsyncClient, seed_user, seed_hospital, seed_order
):
    """无手机号陪诊师接单 → 400 PHONE_REQUIRED"""
    # patient 必须有 phone（否则下单都不会创建出 order）
    patient = await seed_user(phone="13900000111", role=UserRole.patient)
    hospital = await seed_hospital()
    order = await seed_order(patient.id, hospital.id)

    companion = await seed_user(phone=None, role=UserRole.companion)
    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(f"/api/v1/orders/{order.id}/accept")
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PHONE_REQUIRED


# ---------- Companion applying for verification ----------


@pytest.mark.asyncio
async def test_apply_companion_requires_phone(client: AsyncClient, seed_user):
    """无手机号申请陪诊师资质 → 400 PHONE_REQUIRED"""
    user = await seed_user(phone=None, role=UserRole.patient)  # 注册时是 patient
    token = create_access_token({"sub": str(user.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(
        "/api/v1/companions/apply",
        json={
            "real_name": "张三",
            "id_number": "110101199001011234",
            "certifications": "护士资格证",
            "service_area": "北京市朝阳区",
            "service_types": "full_accompany",
            "service_hospitals": "协和医院",
            "service_city": "北京",
            "bio": "测试",
        },
    )
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PHONE_REQUIRED


# ---------- Admin approving a phone-less companion ----------


@pytest.mark.asyncio
async def test_admin_approve_blocked_when_owner_has_no_phone(client: AsyncClient, seed_user):
    """管理员审核通过：陪诊师本人没绑手机号 → 400 PHONE_REQUIRED"""
    owner = await seed_user(phone=None, role=UserRole.companion)
    async with test_session_factory() as session:
        profile = CompanionProfile(
            user_id=owner.id,
            real_name="无手机师傅",
            verification_status=VerificationStatus.pending,
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)

    resp = await client.post(
        f"/api/v1/admin/companions/{profile.id}/approve",
        headers={"X-Admin-Token": "dev-admin-token"},
    )
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PHONE_REQUIRED


@pytest.mark.asyncio
async def test_legacy_error_without_code_still_string(client: AsyncClient, seed_user, seed_hospital):
    """已有 BadRequestException(detail='...') 调用未传 error_code → detail 仍是字符串"""
    # 用一个已知不带 error_code 的旧异常路径：order_id 不存在
    patient = await seed_user(phone="13700001234", role=UserRole.patient)
    token = create_access_token({"sub": str(patient.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/orders/{fake_id}")
    assert resp.status_code == 404
    detail = resp.json().get("detail")
    # 旧路径 detail 应仍是 str（向后兼容）
    assert isinstance(detail, str)


# ---------- Companion without verified profile trying to accept ----------


@pytest.mark.asyncio
async def test_accept_order_requires_verification(
    client: AsyncClient, seed_user, seed_hospital, seed_order
):
    """手机号已绑、却没有 verified profile 的陪诊师接单 → 400 VERIFICATION_REQUIRED"""
    patient = await seed_user(phone="13900000221", role=UserRole.patient)
    hospital = await seed_hospital()
    order = await seed_order(patient.id, hospital.id)

    # 手机号已绑定，但没有 CompanionProfile
    companion = await seed_user(phone="13700000221", role=UserRole.companion)
    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(f"/api/v1/orders/{order.id}/accept")
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.VERIFICATION_REQUIRED


@pytest.mark.asyncio
async def test_accept_order_blocked_for_pending_verification(
    client: AsyncClient, seed_user, seed_hospital, seed_order
):
    """profile 存在但还在 pending，接单同样被 VERIFICATION_REQUIRED 拦"""
    patient = await seed_user(phone="13900000222", role=UserRole.patient)
    hospital = await seed_hospital()
    order = await seed_order(patient.id, hospital.id)

    companion = await seed_user(phone="13700000222", role=UserRole.companion)
    async with test_session_factory() as session:
        profile = CompanionProfile(
            user_id=companion.id,
            real_name="还在审核",
            verification_status=VerificationStatus.pending,
        )
        session.add(profile)
        await session.commit()

    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(f"/api/v1/orders/{order.id}/accept")
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.VERIFICATION_REQUIRED


# ---------- PAYMENT_REQUIRED: start / confirm-start without payment ----------


@pytest.mark.asyncio
async def test_start_order_requires_payment(
    client: AsyncClient, seed_user, seed_hospital, seed_order, seed_companion_profile
):
    """未支付订单陆单后陪诊师调 /start → 400 PAYMENT_REQUIRED"""
    patient = await seed_user(phone="13900000310", role=UserRole.patient)
    hospital = await seed_hospital()
    companion = await seed_user(phone="13700000310", role=UserRole.companion)
    await seed_companion_profile(user_id=companion.id)  # verified
    order = await seed_order(
        patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
    )
    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(f"/api/v1/orders/{order.id}/start")
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PAYMENT_REQUIRED


@pytest.mark.asyncio
async def test_confirm_start_requires_payment(
    client: AsyncClient, seed_user, seed_hospital, seed_order
):
    """未支付订单患者确认开始 → 400 PAYMENT_REQUIRED"""
    patient = await seed_user(phone="13900000320", role=UserRole.patient)
    hospital = await seed_hospital()
    companion = await seed_user(phone="13700000320", role=UserRole.companion)
    order = await seed_order(
        patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted
    )
    token = create_access_token({"sub": str(patient.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    resp = await client.post(f"/api/v1/orders/{order.id}/confirm-start")
    assert resp.status_code == 400, resp.text
    assert _extract_error_code(resp.json()) == error_codes.PAYMENT_REQUIRED
