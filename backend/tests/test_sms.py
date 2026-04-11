"""
SMS Provider tests — covers MockSMSProvider, factory, and provider behavior.
"""

import pytest

from app.services.sms import (
    AliyunSMSProvider,
    MockSMSProvider,
    SMSProvider,
    TencentSMSProvider,
    get_sms_provider,
)


# =============================================================================
# MockSMSProvider
# =============================================================================


@pytest.mark.asyncio
class TestMockSMSProvider:
    """Tests for MockSMSProvider."""

    async def test_send_returns_true(self):
        """Mock provider always returns True."""
        provider = MockSMSProvider()
        result = await provider.send("13800138000", "123456")
        assert result is True

    async def test_send_with_different_phones(self):
        """Mock provider succeeds for any phone number."""
        provider = MockSMSProvider()
        assert await provider.send("13900139000", "999999") is True
        assert await provider.send("18600186000", "000000") is True

    async def test_send_prints_output(self, capsys):
        """Mock provider prints OTP to stdout."""
        provider = MockSMSProvider()
        await provider.send("13800138000", "654321")
        captured = capsys.readouterr()
        assert "13800138000" in captured.out
        assert "654321" in captured.out


# =============================================================================
# Factory function
# =============================================================================


class TestGetSMSProvider:
    """Tests for get_sms_provider factory."""

    def test_default_returns_mock(self, monkeypatch):
        """Default sms_provider='mock' should return MockSMSProvider."""
        monkeypatch.setattr("app.services.sms.settings.sms_provider", "mock")
        provider = get_sms_provider()
        assert isinstance(provider, MockSMSProvider)

    def test_aliyun_returns_aliyun_provider(self, monkeypatch):
        """sms_provider='aliyun' should return AliyunSMSProvider."""
        monkeypatch.setattr("app.services.sms.settings.sms_provider", "aliyun")
        provider = get_sms_provider()
        assert isinstance(provider, AliyunSMSProvider)

    def test_tencent_returns_tencent_provider(self, monkeypatch):
        """sms_provider='tencent' should return TencentSMSProvider."""
        monkeypatch.setattr("app.services.sms.settings.sms_provider", "tencent")
        provider = get_sms_provider()
        assert isinstance(provider, TencentSMSProvider)

    def test_unknown_provider_falls_back_to_mock(self, monkeypatch):
        """Unknown provider name should fall back to MockSMSProvider."""
        monkeypatch.setattr("app.services.sms.settings.sms_provider", "unknown_xyz")
        provider = get_sms_provider()
        assert isinstance(provider, MockSMSProvider)


# =============================================================================
# Provider without credentials (fallback behavior)
# =============================================================================


@pytest.mark.asyncio
class TestProviderFallback:
    """Providers without credentials should fall back gracefully."""

    async def test_aliyun_no_credentials_falls_back(self, monkeypatch):
        """Aliyun provider without credentials prints fallback and returns True."""
        monkeypatch.setattr("app.services.sms.settings.sms_access_key", "")
        monkeypatch.setattr("app.services.sms.settings.sms_access_secret", "")
        monkeypatch.setattr("app.services.sms.settings.sms_sign_name", "")
        monkeypatch.setattr("app.services.sms.settings.sms_template_code", "")
        provider = AliyunSMSProvider()
        result = await provider.send("13800138000", "123456")
        assert result is True

    async def test_tencent_no_credentials_falls_back(self, monkeypatch):
        """Tencent provider without credentials prints fallback and returns True."""
        monkeypatch.setattr("app.services.sms.settings.sms_access_key", "")
        monkeypatch.setattr("app.services.sms.settings.sms_access_secret", "")
        monkeypatch.setattr("app.services.sms.settings.sms_sign_name", "")
        monkeypatch.setattr("app.services.sms.settings.sms_template_code", "")
        monkeypatch.setattr("app.services.sms.settings.sms_sdk_app_id", "")
        provider = TencentSMSProvider()
        result = await provider.send("13800138000", "123456")
        assert result is True


# =============================================================================
# Abstract base
# =============================================================================


@pytest.mark.asyncio
class TestSMSProviderBase:
    """Tests for SMSProvider abstract base class."""

    async def test_base_send_raises_not_implemented(self):
        """Base class send() should raise NotImplementedError."""
        provider = SMSProvider()
        with pytest.raises(NotImplementedError):
            await provider.send("13800138000", "123456")
