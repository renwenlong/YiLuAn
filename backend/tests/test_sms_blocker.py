"""
SMS **阻断级**（blocker）tests — P1-7 / Action #7.

Complementary to ``test_sms_providers.py``. Covers failure modes that
would silently lock users out of OTP login if regressed:

  B1. Provider 缺凭证 fail-fast      —— AliyunProvider without credentials
                                         raises ValueError immediately;
                                         caller must NOT fall back to mock.
  B2. 限流满 → 第 6 条被拒          —— 1h boundary edge (5 → blocked).
  B3. 限流窗口过期 → 放行          —— 60s window expiry; 1h sliding window
                                       eviction.
  B4. 异常路径下手机号脱敏         —— stack trace / log message must mask
                                       the raw phone even on exception.
  B5. OTP 验证幂等                  —— same OTP submitted twice → second
                                       submission rejected (code already
                                       consumed from Redis).
  B6. 空 / 异常手机号              —— "" / "abc" / very-long input must be
                                       rejected by validate, must NOT
                                       consume a rate-limit slot.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.providers.sms import (
    AliyunSMSProvider,
    MockSMSProvider,
    SMSRateLimiter,
    mask_phone_sms,
    reset_inproc_store,
)
from app.utils.outbound import NonRetryableError, reset_circuit_breakers


# ---------------------------------------------------------------------------
# B1. Provider exception is fail-fast (no infinite retry)
# ---------------------------------------------------------------------------

# Note: do NOT decorate this class with @pytest.mark.asyncio — the only test
# inside is sync (it asserts construction-time ValueError), and asyncio_mode=auto
# would otherwise emit PytestWarning about a sync test marked asyncio.
class TestAliyunFailFast:
    """The Aliyun provider must:

    * raise ``ValueError`` immediately when credentials are missing.
    * never silently fall back to mock.
    """

    def test_no_credentials_raises_value_error(self):
        with pytest.raises(ValueError, match="SMS_ACCESS_KEY"):
            AliyunSMSProvider()


# ---------------------------------------------------------------------------
# B2. Rate limit boundary: 6th send blocked
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRateLimitBoundary:
    def setup_method(self):
        reset_inproc_store()

    async def test_sixth_send_in_one_hour_blocked(self, monkeypatch):
        """The 5th send must succeed; the 6th must be rejected with the
        ``per_hour_exceeded`` reason. Using inproc backend with a relaxed
        per-minute limit so we can hit ONLY the 1h cap."""
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_minute_limit",
            lambda: 999,
        )
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_hour_limit",
            lambda: 5,
        )
        limiter = SMSRateLimiter(redis=None)
        phone = "13800138002"
        for i in range(5):
            d = await limiter.check_and_record(phone)
            assert d.allowed is True, f"send #{i+1} unexpectedly blocked: {d}"
        sixth = await limiter.check_and_record(phone)
        assert sixth.allowed is False
        assert sixth.reason == "per_hour_exceeded"
        assert sixth.retry_after_seconds == 3600

    async def test_other_phone_unaffected_by_full_quota(self, monkeypatch):
        """Saturating phone A must NOT bleed into phone B's quota — a
        regression here would let a single noisy user DoS the whole
        site-wide OTP flow."""
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_minute_limit",
            lambda: 999,
        )
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_hour_limit",
            lambda: 5,
        )
        limiter = SMSRateLimiter(redis=None)
        phone_a, phone_b = "13800138003", "13900139003"
        for _ in range(5):
            await limiter.check_and_record(phone_a)
        # A is now saturated; B must still be allowed.
        d_b = await limiter.check_and_record(phone_b)
        assert d_b.allowed is True


# ---------------------------------------------------------------------------
# B3. Window expiry / sliding-window eviction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestRateLimitWindowExpiry:
    def setup_method(self):
        reset_inproc_store()

    async def test_60s_window_expires_then_allows(self, monkeypatch):
        """After the 60s window slides past, a new send must be allowed.
        We do not actually sleep 60s — we mutate the in-process bucket
        so the first send appears 61s old, then re-test."""
        limiter = SMSRateLimiter(redis=None)
        phone = "13800138004"
        first = await limiter.check_and_record(phone)
        assert first.allowed is True
        # Immediately re-test — should be blocked.
        blocked = await limiter.check_and_record(phone)
        assert blocked.allowed is False
        assert blocked.reason == "per_minute_exceeded"

        # Shift the recorded timestamp 65s into the past.
        from app.services.providers.sms.rate_limit import _inproc_store
        _inproc_store[phone] = [t - 65 for t in _inproc_store[phone]]

        # Now should be allowed again.
        retry = await limiter.check_and_record(phone)
        assert retry.allowed is True, (
            "60s window must slide — a send older than 60s must NOT keep "
            "blocking new sends."
        )

    async def test_1h_sliding_window_evicts_old_entries(self, monkeypatch):
        """After 1h all old timestamps must drop, freeing quota."""
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_minute_limit",
            lambda: 999,
        )
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_hour_limit",
            lambda: 5,
        )
        limiter = SMSRateLimiter(redis=None)
        phone = "13800138005"
        for _ in range(5):
            await limiter.check_and_record(phone)
        sixth = await limiter.check_and_record(phone)
        assert sixth.allowed is False

        # Age every entry past 1h.
        from app.services.providers.sms.rate_limit import _inproc_store
        _inproc_store[phone] = [t - 3700 for t in _inproc_store[phone]]

        seventh = await limiter.check_and_record(phone)
        assert seventh.allowed is True, (
            "After 1h sliding window expiry, quota must reset."
        )


# ---------------------------------------------------------------------------
# B4. PII masking on exception path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestPIIMaskOnException:
    """Provider exception path MUST mask the phone in logs / messages."""

    def setup_method(self):
        reset_circuit_breakers()

    async def test_aliyun_exception_message_masks_phone(self, caplog, monkeypatch):
        monkeypatch.setattr("app.config.settings.sms_access_key", "ak")
        monkeypatch.setattr("app.config.settings.sms_access_secret", "sk")
        monkeypatch.setattr("app.config.settings.sms_sign_name", "sig")
        monkeypatch.setattr("app.config.settings.sms_template_code", "TPL")
        provider = AliyunSMSProvider()
        raw_phone = "13800138006"
        masked = mask_phone_sms(raw_phone)

        mock_resp = httpx.Response(
            200,
            json={"Code": "isv.MOBILE_NUMBER_ILLEGAL", "Message": "bad"},
            request=httpx.Request("GET", "https://dysmsapi.aliyuncs.com/"),
        )

        with patch("app.services.providers.sms.aliyun.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with caplog.at_level(logging.ERROR, logger="app.services.providers.sms.aliyun"):
                with pytest.raises(NonRetryableError):
                    await provider.send_otp(raw_phone, "123456")

        log_text = "\n".join(r.getMessage() for r in caplog.records)

        assert raw_phone not in log_text, (
            f"Raw phone {raw_phone} leaked in log: {log_text!r}"
        )
        assert masked in log_text, (
            "Masked phone must appear in the failure log."
        )


# ---------------------------------------------------------------------------
# B5. OTP idempotency (same code accepted only once)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestOTPVerifyIdempotency:
    """A successful verify must DELETE the OTP from Redis so a replay
    (within the 60s window or otherwise) cannot reuse it. This guards
    against an attacker who captured one valid code from a leaked log
    or screenshot.
    """

    async def test_otp_replay_within_window_rejected(self, client, fake_redis):
        """Drives the real /api/v1/auth flow end-to-end."""
        # Disable per-minute rate limit so we can do back-to-back send/verify.
        from app.services.providers.sms import reset_inproc_store as _reset
        _reset()

        # Pre-seed an OTP directly into redis (simulating a successful send).
        phone = "13800138007"
        otp = "654321"
        await fake_redis.set(f"otp:{phone}", otp, ex=300)

        # First verify: must succeed.
        r1 = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": otp},
        )
        assert r1.status_code == 200, r1.text

        # Second verify with the SAME code: must fail because the key
        # was deleted on first success.
        r2 = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": phone, "code": otp},
        )
        assert r2.status_code == 400, (
            f"Replayed OTP must be rejected — got {r2.status_code}: {r2.text}"
        )


# ---------------------------------------------------------------------------
# B6. Bad / empty / over-long phone input
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestBadPhoneInputValidation:
    """An empty or malformed phone MUST be rejected by request
    validation (Pydantic) and MUST NOT count against the rate-limit
    quota — otherwise a single fuzzer can DoS the OTP queue.
    """

    @pytest.mark.parametrize(
        "bad_phone",
        [
            "",
            "abc",
            "1" * 200,        # absurdly long
            "+++",
            "138-0010-001",   # dashes (not E.164/CN)
        ],
    )
    async def test_send_otp_rejects_bad_phone(self, client, fake_redis, bad_phone):
        # Snapshot inproc store before — for parity assertion below.
        from app.services.providers.sms.rate_limit import _inproc_store
        before = dict(_inproc_store)

        resp = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": bad_phone},
        )
        # Must be 4xx (422 or 400). 5xx would mean the validator threw
        # uncaught; 200 would be a serious leak.
        assert 400 <= resp.status_code < 500, (
            f"Bad phone {bad_phone!r} must be rejected with a 4xx, "
            f"got {resp.status_code}: {resp.text}"
        )

        # And the inproc rate-limit store must NOT have grown for that phone.
        assert _inproc_store.get(bad_phone, []) == before.get(bad_phone, []), (
            f"Bad phone {bad_phone!r} consumed a rate-limit slot — "
            "validation must run BEFORE the limiter."
        )


# ---------------------------------------------------------------------------
# Sanity: MockSMSProvider stays well-behaved on edge inputs
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMockProviderEdgeInputs:
    async def test_mock_does_not_crash_on_empty_phone(self, caplog):
        provider = MockSMSProvider()
        # MockProvider must not crash even on degenerate input — we want
        # the validation layer above it to be the gatekeeper, but the
        # provider should also be defensive.
        with caplog.at_level(logging.INFO):
            result = await provider.send_otp("", "123456")
        # Whatever it returns, it must not include raw secrets in logs.
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        assert "123456" not in log_text, (
            "OTP code value must NEVER appear in logs."
        )
        # And ok flag must be a bool either way (no None / exception escape).
        assert isinstance(result.ok, bool)
