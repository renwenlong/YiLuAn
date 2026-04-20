"""
Tests for Aliyun SMS provider real implementation (C5).

Covers:
  1. send_otp success → returns SMSResult with biz_id
  2. Business error isv.MOBILE_NUMBER_ILLEGAL → NonRetryableError
  3. Network timeout → RetryableError (outbound decorator retries)
  4. Missing credentials (empty AccessKeyId) → ValueError at init
  5. Server 500 → RetryableError
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.utils.outbound import NonRetryableError, RetryableError, reset_circuit_breakers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider(monkeypatch):
    """Create an AliyunSMSProvider with fake credentials."""
    monkeypatch.setattr("app.config.settings.sms_access_key", "fake-ak")
    monkeypatch.setattr("app.config.settings.sms_access_secret", "fake-sk")
    monkeypatch.setattr("app.config.settings.sms_sign_name", "医路安")
    monkeypatch.setattr("app.config.settings.sms_template_code", "SMS_000001")
    from app.services.providers.sms.aliyun import AliyunSMSProvider
    return AliyunSMSProvider()


def _mock_response(status_code: int = 200, json_data: dict | None = None):
    """Build a fake httpx.Response."""
    resp = httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("GET", "https://dysmsapi.aliyuncs.com/"),
    )
    return resp


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestAliyunSMSProviderReal:
    def setup_method(self):
        reset_circuit_breakers()

    async def test_send_otp_success(self, monkeypatch):
        """1. Aliyun returns OK → SMSResult(ok=True) with biz_id."""
        provider = _make_provider(monkeypatch)
        mock_resp = _mock_response(200, {"Code": "OK", "BizId": "123456^789"})

        with patch("app.services.providers.sms.aliyun.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            result = await provider.send_otp("13800010001", "666666")

        assert result.ok is True
        assert result.provider == "aliyun"
        assert result.extra["biz_id"] == "123456^789"

    async def test_biz_error_non_retryable(self, monkeypatch):
        """2. isv.MOBILE_NUMBER_ILLEGAL → NonRetryableError."""
        provider = _make_provider(monkeypatch)
        mock_resp = _mock_response(200, {
            "Code": "isv.MOBILE_NUMBER_ILLEGAL",
            "Message": "手机号格式错误",
        })

        with patch("app.services.providers.sms.aliyun.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(NonRetryableError, match="MOBILE_NUMBER_ILLEGAL"):
                await provider.send_otp("999", "123456")

    async def test_network_timeout_retryable(self, monkeypatch):
        """3. Network timeout → RetryableError after outbound retries exhausted."""
        provider = _make_provider(monkeypatch)

        with patch("app.services.providers.sms.aliyun.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.side_effect = httpx.ConnectTimeout("timeout")
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(RetryableError):
                await provider.send_otp("13800010001", "123456")

    async def test_server_500_retryable(self, monkeypatch):
        """5. HTTP 500 → RetryableError."""
        provider = _make_provider(monkeypatch)
        mock_resp = _mock_response(500, {"Code": "InternalError"})

        with patch("app.services.providers.sms.aliyun.httpx.AsyncClient") as MockClient:
            instance = AsyncMock()
            instance.get.return_value = mock_resp
            instance.__aenter__ = AsyncMock(return_value=instance)
            instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = instance

            with pytest.raises(RetryableError):
                await provider.send_otp("13800010001", "123456")

    def test_missing_credentials_raises_at_init(self, monkeypatch):
        """4. Empty AccessKeyId → ValueError at construction time."""
        monkeypatch.setattr("app.config.settings.sms_access_key", "")
        monkeypatch.setattr("app.config.settings.sms_access_secret", "")
        monkeypatch.setattr("app.config.settings.sms_sign_name", "")
        monkeypatch.setattr("app.config.settings.sms_template_code", "")
        from app.services.providers.sms.aliyun import AliyunSMSProvider
        with pytest.raises(ValueError, match="SMS_ACCESS_KEY"):
            AliyunSMSProvider()
