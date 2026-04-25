"""Tests for the Apple Sign-In endpoint and identity-token verifier.

These run with ``APPLE_MOCK_VERIFY=1`` toggled per-test (we patch
``settings.apple_mock_verify`` directly so the global env doesn't leak
between modules). All Apple JWTs are crafted in-test using ``python-jose``
with HS256; mock mode skips signature verification entirely, so the
secret only needs to round-trip the encoder/decoder.

[W18-A]
"""
from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from jose import jwt as jose_jwt

from app.config import settings


APPLE_ISS = "https://appleid.apple.com"
APPLE_AUD = "com.yiluan.app"  # placeholder; matches dev settings.apple_client_id
DUMMY_SECRET = "test-only-secret-not-validated-in-mock-mode"


def make_apple_token(
    *,
    sub: str = "001234.deadbeefcafebabe.0001",
    iss: str = APPLE_ISS,
    aud: str | list[str] | None = APPLE_AUD,
    exp_offset: int = 600,
    extra: dict | None = None,
    drop: tuple[str, ...] = (),
) -> str:
    """Build a synthetic Apple identity token for tests."""
    now = int(time.time())
    claims: dict = {
        "iss": iss,
        "aud": aud,
        "sub": sub,
        "iat": now,
        "exp": now + exp_offset,
        "email": "test@privaterelay.appleid.com",
    }
    if extra:
        claims.update(extra)
    for k in drop:
        claims.pop(k, None)
    return jose_jwt.encode(claims, DUMMY_SECRET, algorithm="HS256")


@pytest.fixture(autouse=True)
def _enable_apple_mock_verify():
    """Force mock verification + a known audience for every test in this module."""
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
# Happy path
# ---------------------------------------------------------------------------
class TestAppleLoginHappyPath:
    async def test_first_login_creates_user(self, client):
        token = make_apple_token(sub="001.first-time-user.000")
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "auth_code_xyz"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        # First-time Apple user has no phone yet — must bind later.
        assert data["user"]["phone"] is None
        assert data["user"]["role"] is None
        assert "id" in data["user"]

    async def test_second_login_reuses_user(self, client):
        sub = "001.repeat-user.000"
        token1 = make_apple_token(sub=sub)
        first = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token1, "authorization_code": "code1"},
        )
        assert first.status_code == 200
        first_id = first.json()["user"]["id"]

        token2 = make_apple_token(sub=sub)
        second = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token2, "authorization_code": "code2"},
        )
        assert second.status_code == 200
        assert second.json()["user"]["id"] == first_id

    async def test_user_info_email_overrides_token_email(self, client):
        token = make_apple_token(sub="001.with-userinfo.000")
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={
                "identity_token": token,
                "authorization_code": "code",
                "user_info": {
                    "email": "person@example.com",
                    "first_name": "Test",
                    "last_name": "User",
                },
            },
        )
        # We don't currently persist email on the user model, but the endpoint
        # MUST accept the user_info bundle without error.
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Claim-validation failures
# ---------------------------------------------------------------------------
class TestAppleLoginClaimErrors:
    async def test_wrong_issuer_rejected(self, client):
        token = make_apple_token(iss="https://attacker.example.com")
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "c"},
        )
        assert resp.status_code == 401
        detail = resp.json()["detail"]
        assert detail["error_code"] == "INVALID_APPLE_TOKEN"

    async def test_expired_token_rejected(self, client):
        # exp 1 hour in the past
        token = make_apple_token(exp_offset=-3600)
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "c"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "APPLE_TOKEN_EXPIRED"

    async def test_missing_sub_rejected(self, client):
        token = make_apple_token(drop=("sub",))
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "c"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "INVALID_APPLE_TOKEN"

    async def test_wrong_audience_rejected(self, client):
        token = make_apple_token(aud="com.someone.else")
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "c"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "INVALID_APPLE_TOKEN"

    async def test_malformed_token_rejected(self, client):
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": "not-a-jwt", "authorization_code": "c"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "INVALID_APPLE_TOKEN"


# ---------------------------------------------------------------------------
# Account-state edge cases
# ---------------------------------------------------------------------------
class TestAppleLoginAccountState:
    async def test_inactive_apple_user_rejected(self, client, seed_user):
        from app.models.user import User
        from tests.conftest import test_session_factory  # type: ignore

        # Seed an inactive user with an existing apple_sub.
        sub = "001.inactive.000"
        async with test_session_factory() as s:
            u = User(apple_sub=sub, is_active=False)
            s.add(u)
            await s.commit()

        token = make_apple_token(sub=sub)
        resp = await client.post(
            "/api/v1/auth/apple/login",
            json={"identity_token": token, "authorization_code": "c"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"]["error_code"] == "APPLE_USER_REVOKED"


# ---------------------------------------------------------------------------
# JWKS path (real verify mode, monkeypatched fetcher) — proves the JWKS
# code path is wired up without ever hitting appleid.apple.com.
# ---------------------------------------------------------------------------
class TestAppleJWKSPath:
    async def test_jwks_unknown_kid_is_invalid(self, client):
        # Switch to real verification mode for this single test.
        settings.apple_mock_verify = False
        try:
            async def fake_jwks():
                return {"keys": [{"kid": "some-other-kid", "kty": "RSA"}]}

            with patch(
                "app.api.v1.auth_apple.fetch_apple_jwks", side_effect=fake_jwks
            ):
                # jose embeds no kid by default; force one in the header.
                now = int(time.time())
                token = jose_jwt.encode(
                    {
                        "iss": APPLE_ISS,
                        "aud": APPLE_AUD,
                        "sub": "001.jwks.000",
                        "iat": now,
                        "exp": now + 600,
                    },
                    DUMMY_SECRET,
                    algorithm="HS256",
                    headers={"kid": "client-side-kid-not-in-jwks"},
                )
                resp = await client.post(
                    "/api/v1/auth/apple/login",
                    json={"identity_token": token, "authorization_code": "c"},
                )
            assert resp.status_code == 401
            assert resp.json()["detail"]["error_code"] == "INVALID_APPLE_TOKEN"
        finally:
            settings.apple_mock_verify = True
