"""
Tests for the new SMS provider abstraction (P0-2, Action #2).

Covers:
  * MockSMSProvider default behavior (no breakage to dev workflow)
  * Factory routing (mock / aliyun / unknown)
  * Aliyun placeholder raises NotImplementedError + log mentions required settings
  * SMSRateLimiter: 60s window (in-process + redis-fake)
  * SMSRateLimiter: 1h window (>=5 sends rejected)
  * Phone masking helper produces "138****0001" form
  * Logs use masked phone (PII redacted)
"""

from __future__ import annotations

import logging

import pytest

from app.services.providers.sms import (
    ALIYUN_REQUIRED_PRODUCTION_SETTINGS,
    AliyunSMSProvider,
    MockSMSProvider,
    SMSProvider,
    SMSRateLimiter,
    SMSResult,
    get_sms_provider,
    mask_phone_sms,
    reset_inproc_store,
)


# ---------------------------------------------------------------------------
# Phone masking
# ---------------------------------------------------------------------------
class TestMaskPhoneSMS:
    def test_basic_cn_phone(self):
        assert mask_phone_sms("13800010001") == "138****0001"

    def test_with_country_code(self):
        # +86 + 11 digits → keep +86, then 138****0001
        assert mask_phone_sms("+8613800010001") == "+86138****0001"

    def test_empty_returns_empty(self):
        assert mask_phone_sms("") == ""
        assert mask_phone_sms(None) == ""

    def test_short_phone(self):
        # too short for 3+4 → still partially masked, never plaintext
        out = mask_phone_sms("12345")
        assert out != "12345"
        assert "*" in out


# ---------------------------------------------------------------------------
# MockSMSProvider
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestMockSMSProvider:
    async def test_send_otp_returns_ok(self):
        provider = MockSMSProvider()
        result = await provider.send_otp("13800010001", "123456")
        assert isinstance(result, SMSResult)
        assert result.ok is True
        assert result.code == "ok"
        assert result.provider == "mock"

    async def test_send_notification_returns_ok(self):
        provider = MockSMSProvider()
        result = await provider.send_notification(
            "13800010001", "TPL_001", {"name": "Alice"}
        )
        assert result.ok is True
        assert result.extra["template_id"] == "TPL_001"

    async def test_log_uses_masked_phone(self, caplog):
        provider = MockSMSProvider()
        with caplog.at_level(logging.INFO, logger="app.services.providers.sms.mock"):
            await provider.send_otp("13800010001", "123456")
        log_text = "\n".join(r.getMessage() for r in caplog.records)
        # PII assertion: masked form present, raw phone NOT present
        assert "138****0001" in log_text
        assert "13800010001" not in log_text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
class TestGetSMSProviderNew:
    def test_default_returns_mock(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.providers.sms.factory.settings.sms_provider", "mock"
        )
        assert isinstance(get_sms_provider(), MockSMSProvider)

    def test_aliyun_returns_aliyun(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.providers.sms.factory.settings.sms_provider", "aliyun"
        )
        monkeypatch.setattr("app.config.settings.sms_access_key", "ak")
        monkeypatch.setattr("app.config.settings.sms_access_secret", "sk")
        monkeypatch.setattr("app.config.settings.sms_sign_name", "sig")
        monkeypatch.setattr("app.config.settings.sms_template_code", "TPL")
        assert isinstance(get_sms_provider(), AliyunSMSProvider)

    def test_unknown_falls_back_to_mock(self, monkeypatch, caplog):
        monkeypatch.setattr(
            "app.services.providers.sms.factory.settings.sms_provider", "weird_xyz"
        )
        with caplog.at_level(logging.WARNING, logger="app.services.providers.sms.factory"):
            provider = get_sms_provider()
        assert isinstance(provider, MockSMSProvider)
        assert any("unknown sms_provider" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Aliyun provider — credential validation
# ---------------------------------------------------------------------------
class TestAliyunCredentialValidation:
    def test_missing_credentials_raises_value_error(self):
        """Without credentials, AliyunSMSProvider() raises ValueError."""
        with pytest.raises(ValueError, match="SMS_ACCESS_KEY"):
            AliyunSMSProvider()

    def test_with_credentials_succeeds(self, monkeypatch):
        """With credentials set, AliyunSMSProvider() initialises."""
        monkeypatch.setattr("app.config.settings.sms_access_key", "ak")
        monkeypatch.setattr("app.config.settings.sms_access_secret", "sk")
        monkeypatch.setattr("app.config.settings.sms_sign_name", "sig")
        monkeypatch.setattr("app.config.settings.sms_template_code", "TPL")
        provider = AliyunSMSProvider()
        assert provider.name == "aliyun"


class TestAliyunRequiredSettings:
    """Checks for the required settings constant."""

    def test_required_production_settings_constant_shape(self):
        assert isinstance(ALIYUN_REQUIRED_PRODUCTION_SETTINGS, tuple)
        assert len(ALIYUN_REQUIRED_PRODUCTION_SETTINGS) >= 4
        for name in ALIYUN_REQUIRED_PRODUCTION_SETTINGS:
            assert name.isupper()
            assert "_" in name


# ---------------------------------------------------------------------------
# Rate limiter (in-process — no Redis needed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSMSRateLimiterInProcess:
    def setup_method(self):
        reset_inproc_store()

    async def test_first_send_allowed(self):
        limiter = SMSRateLimiter(redis=None)
        decision = await limiter.check_and_record("13800010001")
        assert decision.allowed is True
        assert decision.reason == "ok"

    async def test_second_send_within_60s_blocked(self):
        limiter = SMSRateLimiter(redis=None)
        first = await limiter.check_and_record("13800010002")
        second = await limiter.check_and_record("13800010002")
        assert first.allowed is True
        assert second.allowed is False
        assert second.reason == "per_minute_exceeded"
        assert second.retry_after_seconds > 0

    async def test_per_hour_limit(self, monkeypatch):
        # Force per-minute limit to 999 so we ONLY hit the per-hour cap
        # without messing with sleep.
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_minute_limit",
            lambda: 999,
        )
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_hour_limit",
            lambda: 5,
        )
        limiter = SMSRateLimiter(redis=None)
        phone = "13800010003"
        for _ in range(5):
            decision = await limiter.check_and_record(phone)
            assert decision.allowed is True, decision
        sixth = await limiter.check_and_record(phone)
        assert sixth.allowed is False
        assert sixth.reason == "per_hour_exceeded"

    async def test_different_phones_independent(self):
        limiter = SMSRateLimiter(redis=None)
        a = await limiter.check_and_record("13800010004")
        b = await limiter.check_and_record("13900010004")
        assert a.allowed is True
        assert b.allowed is True


# ---------------------------------------------------------------------------
# Rate limiter (FakeRedis-backed)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSMSRateLimiterRedis:
    async def test_60s_window_with_fake_redis(self, fake_redis):
        limiter = SMSRateLimiter(redis=fake_redis)
        phone = "13800010005"
        first = await limiter.check_and_record(phone)
        second = await limiter.check_and_record(phone)
        assert first.allowed is True
        assert second.allowed is False
        assert second.reason == "per_minute_exceeded"

    async def test_1h_window_with_fake_redis(self, fake_redis, monkeypatch):
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_minute_limit",
            lambda: 999,
        )
        monkeypatch.setattr(
            "app.services.providers.sms.rate_limit._per_hour_limit",
            lambda: 5,
        )
        limiter = SMSRateLimiter(redis=fake_redis)
        phone = "13800010006"
        for _ in range(5):
            decision = await limiter.check_and_record(phone)
            assert decision.allowed is True
        sixth = await limiter.check_and_record(phone)
        assert sixth.allowed is False
        assert sixth.reason == "per_hour_exceeded"


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
class TestSMSProviderBaseNew:
    async def test_base_send_otp_raises(self):
        with pytest.raises(NotImplementedError):
            await SMSProvider().send_otp("13800010001", "123456")

    async def test_base_send_notification_raises(self):
        with pytest.raises(NotImplementedError):
            await SMSProvider().send_notification("13800010001", "TPL", {})
