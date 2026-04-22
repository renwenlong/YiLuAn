"""End-to-end test for the PHONE_REQUIRED error-code link.

Verifies the full UX-driving link from frontend's perspective:

1. A patient without a bound phone tries to create an order.
2. Backend returns HTTP 400 with machine-readable
   ``detail = {"error_code": "PHONE_REQUIRED", "message": ...}``.
3. After the patient binds a phone (simulated via direct DB write that
   mirrors the OTP-verify code path), the same request succeeds.

This covers the contract that ``wechat/services/request.js`` and
``ios/YiLuAn/Core/Networking/APIClient.swift`` rely on to drive the
bind-phone bottom sheet.

Companion paths (accept order / apply for verification) are unit-covered
in ``test_phone_required_guards.py``; this file focuses on the patient
order link and the recovery flow because that's what 99% of users hit
on first launch.
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core import error_codes
from app.core.security import create_access_token
from app.models.user import UserRole
from tests.conftest import test_session_factory


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
async def test_phone_required_e2e_blocks_then_unblocks(
    client: AsyncClient, seed_user, seed_hospital
):
    """E2E: 未绑定手机号下单被拦截 → 绑定后同一请求成功。"""
    # --- 1. seed an unbound patient and authenticate ---
    patient = await seed_user(phone=None, role=UserRole.patient)
    token = create_access_token({"sub": str(patient.id), "role": "patient"})
    client.headers["Authorization"] = f"Bearer {token}"

    hospital = await seed_hospital()
    body = {
        "service_type": "full_accompany",
        "hospital_id": str(hospital.id),
        "appointment_date": "2027-05-01",
        "appointment_time": "09:00",
    }

    # --- 2. blocked by PHONE_REQUIRED ---
    blocked = await client.post("/api/v1/orders", json=body)
    assert blocked.status_code == 400, blocked.text
    payload = blocked.json()
    assert _detail_error_code(payload) == error_codes.PHONE_REQUIRED
    msg = _detail_message(payload)
    assert msg is not None and len(msg) > 0, "error message must be non-empty for UI"

    # --- 3. simulate phone binding (mirrors what /api/v1/auth/verify does) ---
    async with test_session_factory() as session:
        from sqlalchemy import select

        from app.models.user import User as UserModel

        result = await session.execute(select(UserModel).where(UserModel.id == patient.id))
        user_row = result.scalar_one()
        user_row.phone = "13800000099"
        await session.commit()

    # --- 4. same request now succeeds ---
    ok = await client.post("/api/v1/orders", json=body)
    assert ok.status_code in (200, 201), ok.text
    body_ok = ok.json()
    assert body_ok.get("patient_id") == str(patient.id)
    assert body_ok.get("status") == "created"


@pytest.mark.asyncio
async def test_phone_required_payload_shape(client: AsyncClient, seed_user, seed_hospital):
    """E2E contract: response shape exactly matches frontend dispatcher expectation."""
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
    assert resp.status_code == 400
    payload = resp.json()

    # contract: detail must be an object with both keys
    detail = payload.get("detail")
    assert isinstance(detail, dict), "detail must be a dict for new-style error codes"
    assert detail.get("error_code") == error_codes.PHONE_REQUIRED
    assert isinstance(detail.get("message"), str)
