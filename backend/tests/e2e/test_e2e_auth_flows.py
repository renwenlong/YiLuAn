"""E2E: authentication flows.

Covers:
  * OTP send + verify (registration on first call, login on second)
  * Refresh token round-trip
  * Apple Sign-In via mock-verify mode (reuses fixtures from PR #16)
  * Token validation: invalid/expired token rejected
"""
from __future__ import annotations

import time

import pytest
from jose import jwt as jose_jwt

from app.config import settings

pytestmark = pytest.mark.e2e


APPLE_ISS = "https://appleid.apple.com"
APPLE_AUD = "com.yiluan.app"
DUMMY_SECRET = "test-only-secret-not-validated-in-mock-mode"


def _make_apple_token(sub: str, *, exp_offset: int = 600, email: str | None = None) -> str:
    now = int(time.time())
    claims = {
        "iss": APPLE_ISS,
        "aud": APPLE_AUD,
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
    }
    if email:
        claims["email"] = email
    return jose_jwt.encode(claims, DUMMY_SECRET, algorithm="HS256")


@pytest.fixture
def _enable_apple_mock_verify():
    original_mock = settings.apple_mock_verify
    original_aud = settings.apple_client_id
    settings.apple_mock_verify = True
    settings.apple_client_id = APPLE_AUD
    try:
        yield
    finally:
        settings.apple_mock_verify = original_mock
        settings.apple_client_id = original_aud


# ---------------------------------------------------------------------------
# OTP login
# ---------------------------------------------------------------------------
async def test_otp_register_then_login(e2e_client, fake_redis, login_via_otp, patient_phone):
    # First call -> creates user.
    access1, refresh1, user1 = await login_via_otp(patient_phone)
    assert access1 and refresh1
    assert user1["phone"] == patient_phone

    # Second call (different "session") -> same user reused.
    access2, refresh2, user2 = await login_via_otp(patient_phone)
    assert user2["id"] == user1["id"]
    # Tokens are valid JWTs (may be byte-identical when issued in the same
    # second since payload sub/iat/exp/type/role match — that's expected).
    assert access2.count(".") == 2 and refresh2.count(".") == 2


async def test_otp_invalid_code_rejected(e2e_client, fake_redis, patient_phone):
    # Clear any rate-limit keys.
    for key in (
        f"otp:rate:{patient_phone}",
        f"sms:rate:per_minute:{patient_phone}",
        f"sms:rate:per_hour:{patient_phone}",
    ):
        await fake_redis.delete(key)

    r = await e2e_client.post("/api/v1/auth/send-otp", json={"phone": patient_phone})
    assert r.status_code == 200, r.text

    r = await e2e_client.post(
        "/api/v1/auth/verify-otp",
        json={"phone": patient_phone, "code": "999999"},
    )
    assert r.status_code == 400


async def test_refresh_token_roundtrip(e2e_client, login_via_otp, patient_phone):
    access, refresh, _ = await login_via_otp(patient_phone)

    r = await e2e_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh}
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["refresh_token"]
    # Refresh issues a fresh token (may be byte-identical to the source when
    # issued in the same second since payload sub/exp/type match — that's OK).
    assert data["refresh_token"].count(".") == 2


async def test_refresh_with_access_token_rejected(e2e_client, login_via_otp, patient_phone):
    access, _, _ = await login_via_otp(patient_phone)
    r = await e2e_client.post("/api/v1/auth/refresh", json={"refresh_token": access})
    assert r.status_code == 401


async def test_refresh_with_garbage_token_rejected(e2e_client):
    r = await e2e_client.post(
        "/api/v1/auth/refresh", json={"refresh_token": "not.a.real.jwt"}
    )
    assert r.status_code == 401


async def test_protected_endpoint_without_token(e2e_client):
    r = await e2e_client.get("/api/v1/companions/me")
    # FastAPI's HTTPBearer returns 403 when header is missing.
    assert r.status_code in (401, 403)


async def test_protected_endpoint_with_garbage_token(e2e_client):
    r = await e2e_client.get(
        "/api/v1/companions/me",
        headers={"Authorization": "Bearer not.a.real.jwt"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Apple Sign-In (mock verify)
# ---------------------------------------------------------------------------
async def test_apple_login_first_creates_user(e2e_client, _enable_apple_mock_verify):
    sub = f"e2e.apple.first.{int(time.time()*1000)}"
    token = _make_apple_token(sub, email="user@privaterelay.appleid.com")
    r = await e2e_client.post(
        "/api/v1/auth/apple/login",
        json={"identity_token": token, "authorization_code": "auth_code_xyz"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["access_token"]
    assert data["refresh_token"]
    assert data["user"]["phone"] is None  # Apple users start without phone.


async def test_apple_login_repeat_reuses_user(e2e_client, _enable_apple_mock_verify):
    sub = f"e2e.apple.repeat.{int(time.time()*1000)}"
    tok1 = _make_apple_token(sub)
    r1 = await e2e_client.post(
        "/api/v1/auth/apple/login",
        json={"identity_token": tok1, "authorization_code": "code1"},
    )
    assert r1.status_code == 200
    uid = r1.json()["user"]["id"]

    tok2 = _make_apple_token(sub)
    r2 = await e2e_client.post(
        "/api/v1/auth/apple/login",
        json={"identity_token": tok2, "authorization_code": "code2"},
    )
    assert r2.status_code == 200
    assert r2.json()["user"]["id"] == uid


async def test_apple_login_expired_token_rejected(e2e_client, _enable_apple_mock_verify):
    token = _make_apple_token("e2e.apple.expired", exp_offset=-60)
    r = await e2e_client.post(
        "/api/v1/auth/apple/login",
        json={"identity_token": token, "authorization_code": "x"},
    )
    assert r.status_code == 401
