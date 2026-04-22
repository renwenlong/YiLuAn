"""End-to-end test for the PAYMENT_REQUIRED error-code link.

The pre-payment guard appears in two service flows:

1. Companion calls ``POST /api/v1/orders/{id}/start`` to begin service.
2. Patient calls ``POST /api/v1/orders/{id}/confirm-start`` to confirm
   the companion's request to start.

Both must reject with HTTP 400 + ``error_code = PAYMENT_REQUIRED`` when
no successful payment exists for the order. After we seed a successful
payment row (mirroring what the WeChat Pay callback does), the same
endpoints succeed.

This is the contract the iOS / 微信小程序 dispatchers rely on to drive
the "去支付" guide card.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core import error_codes
from app.core.security import create_access_token
from app.models.order import OrderStatus
from app.models.user import UserRole


def _detail_error_code(payload: dict) -> str | None:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail.get("error_code")
    return None


def _detail_message(payload: dict) -> str | None:
    detail = payload.get("detail")
    if isinstance(detail, dict):
        return detail.get("message")
    return detail if isinstance(detail, str) else None


@pytest.mark.asyncio
async def test_payment_required_e2e_companion_start(
    client: AsyncClient, seed_user, seed_hospital, seed_order, seed_payment
):
    """E2E: 陪诊师未付款情况下 POST /orders/{id}/start → 400 PAYMENT_REQUIRED；付款后成功。"""
    patient = await seed_user(phone="13800000001", role=UserRole.patient)
    companion = await seed_user(phone="13900000001", role=UserRole.companion)
    hospital = await seed_hospital()
    order = await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        companion_id=companion.id,
        status=OrderStatus.accepted,
    )

    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"

    # --- 1. blocked because no payment row exists ---
    blocked = await client.post(f"/api/v1/orders/{order.id}/start")
    assert blocked.status_code == 400, blocked.text
    payload = blocked.json()
    assert _detail_error_code(payload) == error_codes.PAYMENT_REQUIRED
    msg = _detail_message(payload)
    assert msg and len(msg) > 0, "error message must be non-empty for guide card"

    # --- 2. seed a successful payment, then retry ---
    await seed_payment(
        order_id=order.id, user_id=patient.id, amount=299.0, payment_type="pay", status="success"
    )
    ok = await client.post(f"/api/v1/orders/{order.id}/start")
    assert ok.status_code in (200, 201), ok.text
    body = ok.json()
    assert body.get("status") == OrderStatus.in_progress.value


@pytest.mark.asyncio
async def test_payment_required_e2e_patient_confirm_start(
    client: AsyncClient, seed_user, seed_hospital, seed_order, seed_payment
):
    """E2E: 患者未付款情况下 POST /orders/{id}/confirm-start → 400 PAYMENT_REQUIRED；付款后成功。"""
    patient = await seed_user(phone="13800000002", role=UserRole.patient)
    companion = await seed_user(phone="13900000002", role=UserRole.companion)
    hospital = await seed_hospital()
    order = await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        companion_id=companion.id,
        status=OrderStatus.accepted,
    )

    token = create_access_token({"sub": str(patient.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    blocked = await client.post(f"/api/v1/orders/{order.id}/confirm-start")
    assert blocked.status_code == 400, blocked.text
    payload = blocked.json()
    assert _detail_error_code(payload) == error_codes.PAYMENT_REQUIRED

    await seed_payment(
        order_id=order.id, user_id=patient.id, amount=299.0, payment_type="pay", status="success"
    )
    ok = await client.post(f"/api/v1/orders/{order.id}/confirm-start")
    assert ok.status_code in (200, 201), ok.text
    body = ok.json()
    assert body.get("status") == OrderStatus.in_progress.value


@pytest.mark.asyncio
async def test_payment_required_payload_shape(
    client: AsyncClient, seed_user, seed_hospital, seed_order
):
    """Contract: detail must be {"error_code": "PAYMENT_REQUIRED", "message": str}."""
    patient = await seed_user(phone="13800000003", role=UserRole.patient)
    companion = await seed_user(phone="13900000003", role=UserRole.companion)
    hospital = await seed_hospital()
    order = await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        companion_id=companion.id,
        status=OrderStatus.accepted,
    )

    token = create_access_token({"sub": str(companion.id), "role": "companion"})
    client.headers["Authorization"] = f"Bearer {token}"
    resp = await client.post(f"/api/v1/orders/{order.id}/start")
    assert resp.status_code == 400
    payload = resp.json()
    detail = payload.get("detail")
    assert isinstance(detail, dict), "detail must be dict for new-style error codes"
    assert detail.get("error_code") == error_codes.PAYMENT_REQUIRED
    assert isinstance(detail.get("message"), str)
