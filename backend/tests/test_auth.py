import uuid
from datetime import datetime, timedelta, timezone

import pytest
import jwt

from app.config import settings
from app.core.security import create_access_token, create_refresh_token, decode_token


# ===========================================================================
# POST /api/v1/auth/send-otp
# ===========================================================================
class TestSendOTP:
    async def test_send_otp_success(self, client, fake_redis):
        response = await client.post(
            "/api/v1/auth/send-otp", json={"phone": "13800138000"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "OTP sent successfully"
        # OTP should be stored in Redis
        otp = await fake_redis.get("otp:13800138000")
        assert otp is not None
        assert len(otp) == 6
        assert otp.isdigit()

    async def test_send_otp_rate_limit(self, client, fake_redis):
        # First request succeeds
        response1 = await client.post(
            "/api/v1/auth/send-otp", json={"phone": "13800138000"}
        )
        assert response1.status_code == 200
        # Second request within 60s fails
        response2 = await client.post(
            "/api/v1/auth/send-otp", json={"phone": "13800138000"}
        )
        assert response2.status_code == 400
        assert "60 seconds" in response2.json()["detail"]

    async def test_send_otp_invalid_phone_short(self, client):
        response = await client.post(
            "/api/v1/auth/send-otp", json={"phone": "1234"}
        )
        assert response.status_code == 422

    async def test_send_otp_invalid_phone_letters(self, client):
        response = await client.post(
            "/api/v1/auth/send-otp", json={"phone": "138abc38000"}
        )
        assert response.status_code == 422

    async def test_send_otp_invalid_phone_empty(self, client):
        response = await client.post(
            "/api/v1/auth/send-otp", json={"phone": ""}
        )
        assert response.status_code == 422


# ===========================================================================
# POST /api/v1/auth/verify-otp
# ===========================================================================
class TestVerifyOTP:
    async def test_verify_otp_new_user(self, client, fake_redis):
        # Pre-store OTP
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["phone"] == "13800138000"
        assert data["user"]["role"] is None  # new user, no role
        assert "id" in data["user"]
        # OTP should be deleted after use
        otp = await fake_redis.get("otp:13800138000")
        assert otp is None

    async def test_verify_otp_existing_user(self, client, fake_redis, seed_user):
        user = await seed_user(phone="13800138000")
        await fake_redis.set("otp:13800138000", "654321", ex=300)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "654321"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["id"] == str(user.id)

    async def test_verify_otp_wrong_code(self, client, fake_redis):
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "999999"},
        )
        assert response.status_code == 400
        assert "Invalid OTP" in response.json()["detail"]

    async def test_verify_otp_expired(self, client):
        # No OTP in Redis (simulates expiry)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 400
        assert "expired" in response.json()["detail"].lower()

    async def test_verify_otp_dev_bypass(self, client):
        # Dev mode: code "000000" always works, no Redis entry needed
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "000000"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["phone"] == "13800138000"

    async def test_verify_otp_invalid_code_format(self, client):
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "12345"},
        )
        assert response.status_code == 422

    async def test_verify_otp_disabled_user(self, client, fake_redis, seed_user):
        await seed_user(phone="13800138000", is_active=False)
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "123456"},
        )
        assert response.status_code == 401
        assert "disabled" in response.json()["detail"].lower()

    async def test_verify_otp_returns_valid_tokens(self, client, fake_redis):
        await fake_redis.set("otp:13800138000", "123456", ex=300)
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "13800138000", "code": "123456"},
        )
        data = response.json()
        # Decode and verify access token
        access_payload = decode_token(data["access_token"])
        assert access_payload is not None
        assert access_payload["type"] == "access"
        assert "sub" in access_payload
        # Decode and verify refresh token
        refresh_payload = decode_token(data["refresh_token"])
        assert refresh_payload is not None
        assert refresh_payload["type"] == "refresh"
        assert refresh_payload["sub"] == access_payload["sub"]


# ===========================================================================
# POST /api/v1/auth/refresh
# ===========================================================================
class TestRefreshToken:
    async def _issue_refresh(self, client, user):
        """Mint a refresh token AND register its jti in FakeRedis.

        Mirrors what AuthService._issue_token_pair does in real flows. Tests
        that need a 'genuinely valid' refresh should use this helper instead
        of calling create_refresh_token directly.
        """
        from app.services.refresh_tokens import RefreshTokenStore

        jti = uuid.uuid4().hex
        token = create_refresh_token({"sub": str(user.id), "role": None}, jti=jti)
        store = RefreshTokenStore(client._transport.app.state.redis)
        await store.issue(str(user.id), jti, ttl_seconds=3600)
        return token, jti

    async def test_refresh_success(self, client, seed_user):
        user = await seed_user(phone="13800138000")
        refresh, _jti = await self._issue_refresh(client, user)
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        new_access = decode_token(data["access_token"])
        assert new_access["sub"] == str(user.id)
        assert new_access["type"] == "access"
        # New refresh must carry a fresh jti, not the old one.
        new_refresh = decode_token(data["refresh_token"])
        assert new_refresh["type"] == "refresh"
        assert "jti" in new_refresh

    async def test_refresh_rotates_jti_and_invalidates_old(self, client, seed_user):
        """Single-use guarantee: replaying the old refresh after a successful
        rotation must be rejected (and triggers revoke_all under the hood).
        """
        user = await seed_user(phone="13800138001")
        refresh, _ = await self._issue_refresh(client, user)
        first = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert first.status_code == 200
        # Replay old refresh -> reuse detected -> 401
        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert replay.status_code == 401
        assert "reuse" in replay.json()["detail"].lower()

    async def test_refresh_reuse_revokes_all_sessions(self, client, seed_user):
        """After reuse-detection, every other live refresh for the same user
        must also be invalidated (kill-all-sessions strategy / RFC 6819).
        """
        user = await seed_user(phone="13800138002")
        # Two independent logins (two devices).
        refresh_a, _ = await self._issue_refresh(client, user)
        refresh_b, _ = await self._issue_refresh(client, user)
        # Rotate A successfully.
        ok = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
        )
        assert ok.status_code == 200
        # Replay A => reuse => kill all (including B).
        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_a}
        )
        assert replay.status_code == 401
        # B should now also be dead.
        b_resp = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh_b}
        )
        assert b_resp.status_code == 401

    async def test_refresh_legacy_token_without_jti_rejected(
        self, client, seed_user
    ):
        """Tokens minted before the rotation feature (no ``jti`` claim) must
        be rejected so we don't leave a 7-day replay hole during rollout.
        """
        user = await seed_user(phone="13800138003")
        legacy = create_refresh_token({"sub": str(user.id), "role": None})
        # Strip jti by re-encoding manually.
        import jwt as _jwt

        payload = _jwt.decode(
            legacy, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
        payload.pop("jti", None)
        no_jti = _jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": no_jti}
        )
        assert response.status_code == 401
        assert "jti" in response.json()["detail"].lower()

    async def test_refresh_invalid_token(self, client):
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "garbage-token-string"}
        )
        assert response.status_code == 401

    async def test_refresh_expired_token(self, client, seed_user):
        user = await seed_user(phone="13800138000")
        expired_payload = {
            "sub": str(user.id),
            "role": None,
            "type": "refresh",
            "jti": uuid.uuid4().hex,
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": expired_token}
        )
        assert response.status_code == 401

    async def test_refresh_with_access_token(self, client, seed_user):
        user = await seed_user(phone="13800138000")
        access = create_access_token({"sub": str(user.id), "role": None})
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": access}
        )
        assert response.status_code == 401
        assert "token type" in response.json()["detail"].lower()

    async def test_refresh_user_not_found(self, client):
        fake_id = str(uuid.uuid4())
        refresh = create_refresh_token({"sub": fake_id, "role": None})
        response = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": refresh}
        )
        assert response.status_code == 401
        assert "not found" in response.json()["detail"].lower()


# ===========================================================================
# Token security edge cases
# ===========================================================================
class TestTokenSecurity:
    async def test_token_without_sub(self, client):
        token = jwt.encode(
            {"type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        response = await client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401

    async def test_malformed_token(self, client):
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer not.a.real.jwt.token"},
        )
        assert response.status_code == 401

    async def test_token_for_disabled_user(self, client, seed_user):
        user = await seed_user(phone="13800138000", is_active=False)
        token = create_access_token({"sub": str(user.id), "role": None})
        response = await client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401
        assert "disabled" in response.json()["detail"].lower()


# ===========================================================================
# OTP brute-force protection
# ===========================================================================
class TestOTPBruteForceProtection:
    """P0-01: 5 failed OTP attempts → 15 min lockout."""

    PHONE = "13800139999"
    OTP_KEY = f"otp:{PHONE}"
    FAIL_KEY = f"otp:fail:{PHONE}"

    async def test_valid_otp_succeeds(self, client, fake_redis):
        await fake_redis.set(self.OTP_KEY, "123456", ex=300)
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": self.PHONE, "code": "123456"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_failed_attempts_under_limit(self, client, fake_redis):
        await fake_redis.set(self.OTP_KEY, "123456", ex=300)
        for _ in range(4):
            resp = await client.post(
                "/api/v1/auth/verify-otp",
                json={"phone": self.PHONE, "code": "000001"},
            )
            assert resp.status_code == 400

    async def test_fifth_failure_triggers_lockout(self, client, fake_redis):
        await fake_redis.set(self.OTP_KEY, "123456", ex=300)
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/verify-otp",
                json={"phone": self.PHONE, "code": "000001"},
            )
        # 5th attempt itself returns 400, but now locked
        assert resp.status_code == 400
        # Next attempt should be 429
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": self.PHONE, "code": "000001"},
        )
        assert resp.status_code == 429
        assert "Too many failed attempts" in resp.json()["detail"]

    async def test_lockout_blocks_correct_code(self, client, fake_redis):
        # Simulate 5 failures
        await fake_redis.set(self.FAIL_KEY, "5")
        await fake_redis.expire(self.FAIL_KEY, 900)
        await fake_redis.set(self.OTP_KEY, "123456", ex=300)
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": self.PHONE, "code": "123456"},
        )
        assert resp.status_code == 429

    async def test_success_clears_fail_counter(self, client, fake_redis):
        # Accumulate 3 failures
        await fake_redis.set(self.OTP_KEY, "123456", ex=300)
        for _ in range(3):
            await client.post(
                "/api/v1/auth/verify-otp",
                json={"phone": self.PHONE, "code": "000001"},
            )
        count = await fake_redis.get(self.FAIL_KEY)
        assert int(count) == 3
        # Now succeed (OTP is still there for wrong-code failures)
        resp = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": self.PHONE, "code": "123456"},
        )
        assert resp.status_code == 200
        # Counter should be cleared
        count = await fake_redis.get(self.FAIL_KEY)
        assert count is None
