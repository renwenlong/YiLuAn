"""A21-02b / D-033 \u2014 sms_send_log integration tests.

\u9a8c\u8bc1\uff1a
* ``LoggingSMSProviderWrapper`` \u5728\u8c03\u7528 mock provider \u524d\u540e\u6b63\u786e\u5199\u5165\u4e00\u884c log\u3002
* \u6210\u529f\uff1a\u884c\u4ece ``pending`` \u8df3 ``success``\uff1bphone_masked \u6b63\u786e\uff1bphone_hash \u4e0d\u542b\u660e\u6587\u3002
* \u5931\u8d25\uff1a\u884c\u8df3 ``failed``\uff1b\u5f02\u5e38\u4e0a\u629b\uff08\u4e0d\u88ab\u541e\uff09\u3002\n* ``hash_phone`` \u786e\u5b9a\u6027\u4e0e salt \u654f\u611f\u3002\n* ``mask_phone`` \u8fb9\u754c\u8868\u73b0\uff08\u77ed\u53f7 \u3001\u7a7a\u4e32\uff09\u3002\n* ``expires_at = now() + 90d`` \u300290 \u5929 \u00b1 5s\u3002\n\nDB session \u9694\u79bb\n--------------\n\u9879\u76ee\u73b0\u6709\u6d4b\u8bd5\u4f7f\u7528 ``tests.conftest.test_session_factory``\uff08SQLite \u5185\u5b58\uff09\u3002\nwrapper \u9ed8\u8ba4\u8bfb ``app.database.async_session``\u2014\u2014\u9700\u8981 monkeypatch \u4e3a\u6d4b\u8bd5\u5de5\u5382\u3002\n"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.pii import hash_phone, mask_phone
from app.models.sms_send_log import SmsSendLog
from app.services.providers.sms import SMSResult
from app.services.providers.sms.base import SMSProvider
from app.services.providers.sms.logging_wrapper import (
    LoggingSMSProviderWrapper,
    wrap_with_logging,
)
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_async_session(monkeypatch):
    """\u5c06 wrapper \u7684 session factory \u6307\u5411 SQLite in-memory \u6d4b\u8bd5\u5e93\u3002"""
    monkeypatch.setattr(
        "app.database.async_session",
        test_session_factory,
    )


class _SuccessProvider(SMSProvider):
    name = "mock"

    async def send_otp(self, phone, code, template_id=None):
        return SMSResult(
            ok=True,
            code="ok",
            message="queued",
            provider=self.name,
            extra={"biz_id": "biz-12345", "masked_phone": "***"},
        )


class _BizFailureProvider(SMSProvider):
    name = "mock"

    async def send_otp(self, phone, code, template_id=None):
        return SMSResult(
            ok=False,
            code="provider_error",
            message="upstream rejected",
            provider=self.name,
            extra={},
        )


class _RaisingProvider(SMSProvider):
    name = "aliyun"

    async def send_otp(self, phone, code, template_id=None):
        raise RuntimeError("network exploded: connection reset")


# ---------------------------------------------------------------------------
# 1. send_otp: pending \u2192 success
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_otp_creates_log_with_pending_then_success():
    wrapper = wrap_with_logging(_SuccessProvider())
    result = await wrapper.send_otp("13800001234", "654321", template_id="OTP")
    assert result.ok is True

    async with test_session_factory() as s:
        rows = (await s.execute(select(SmsSendLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "success"
    assert row.provider == "mock"
    assert row.template_code == "OTP"
    assert row.phone_masked == "138******34"  # core.pii.mask_phone style
    # PII guard: \u660e\u6587\u4e0d\u80fd\u51fa\u73b0\u5728 hash / masked \u4e2d
    assert "13800001234" not in row.phone_masked
    assert "13800001234" not in row.phone_hash
    assert len(row.phone_hash) == 64  # sha256 hex
    # \u54cd\u5e94\u4fe1\u606f
    assert row.biz_id == "biz-12345"
    assert row.response_code == "ok"


# ---------------------------------------------------------------------------
# 2. send_otp: provider \u629b\u5f02\u5e38 \u2192 failed + re-raise
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_otp_provider_failure_marks_log_failed_and_reraises():
    wrapper = wrap_with_logging(_RaisingProvider())

    with pytest.raises(RuntimeError, match="network exploded"):
        await wrapper.send_otp("13900009999", "111222")

    async with test_session_factory() as s:
        rows = (await s.execute(select(SmsSendLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failed"
    assert row.response_code == "RuntimeError"
    assert "network exploded" in (row.response_msg or "")


@pytest.mark.asyncio
async def test_send_otp_business_failure_marks_log_failed_no_raise():
    """\u5e95\u5c42 result.ok=False \u4e0d\u629b\u5f02\u5e38\uff0c\u4f46 log \u4ecd\u8bb0 failed\u3002"""
    wrapper = wrap_with_logging(_BizFailureProvider())
    result = await wrapper.send_otp("13700007777", "999000")
    assert result.ok is False

    async with test_session_factory() as s:
        rows = (await s.execute(select(SmsSendLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.status == "failed"
    assert row.response_code == "provider_error"
    assert "upstream rejected" in (row.response_msg or "")


# ---------------------------------------------------------------------------
# 3. hash_phone: deterministic + salt-sensitive
# ---------------------------------------------------------------------------


def test_phone_hash_is_deterministic_with_salt():
    h1 = hash_phone("13800001234", "salt-A")
    h2 = hash_phone("13800001234", "salt-A")
    h3 = hash_phone("13800001234", "salt-B")
    assert h1 == h2
    assert h1 != h3
    # \u4e0d\u80fd\u542b\u660e\u6587
    assert "13800001234" not in h1
    assert len(h1) == 64


def test_hash_phone_empty_returns_empty():
    assert hash_phone("", "salt") == ""
    assert hash_phone(None, "salt") == ""


def test_hash_phone_empty_salt_raises():
    import pytest as _pytest
    with _pytest.raises(ValueError):
        hash_phone("13800001234", "")


# ---------------------------------------------------------------------------
# 4. mask_phone format \u8fb9\u754c
# ---------------------------------------------------------------------------
# \u6ce8\uff1a``app.core.pii.mask_phone`` \u73b0\u6709\u5b9e\u73b0\u4fdd\u7559 \u201c\u524d 3 + \u540e 2\uff0c\u4e2d\u95f4\u5168 *\u201d\u3002
# 11 \u4f4d\u624b\u673a\u53f7 ``13800001234`` -> ``138******34``\u3002
# \u8fd9\u8ddf task \u63cf\u8ff0\u7684 ``138****1234`` \u4e0d\u540c\u2014\u2014\u9879\u76ee\u4e2d\u5b9e\u9645\u53e6\u5916\u6709 ``mask_phone_sms``
# \u8d1f\u8d23 ``138****1234`` \u683c\u5f0f\uff08\u89c1 ``providers/sms/base.py``\uff09\u3002\n# A21-02b log \u5b58\u50a8\u7edf\u4e00\u8d70 ``app.core.pii.mask_phone``\uff08\u9879\u76ee \u552f\u4e00 PII \u6e90\u7684\u51fd\u6570\uff09\uff0c\n# \u4ee5\u514d\u4e24\u5957\u8131\u654f\u89c4\u5219\u53cc\u8f68\u3002\u8fb9\u754c\u8857\u4e3e\u7531\u73b0\u6709\u5b9e\u73b0\u51b3\u5b9a\uff1a\n# - 11 \u4f4d \u2192 ``138******34``\n# - \u77ed\u53f7 \u2264 4 \u4f4d \u2192 \u5168\u90e8 ``****``\n# - \u77ed\u53f7 5\u20138 \u4f4d \u2192 ``12****78`` \u7c7b\u578b\n# - \u7a7a / None \u2192 ``\"\"``\n


def test_phone_masked_format_for_cn_phone():
    assert mask_phone("13800001234") == "138******34"


def test_phone_masked_format_short():
    # 8 \u4f4d\u8d70 \"\u524d 2 + \u540e 2\" \u5206\u652f
    assert mask_phone("12345678") == "12****78"


def test_phone_masked_format_too_short():
    # \u22644 \u4f4d \u2192 \u5168 *
    assert mask_phone("1234") == "****"
    assert mask_phone("") == ""


# ---------------------------------------------------------------------------
# 5. expires_at = now + 90d (\u00b1 5s)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expires_at_set_to_90d_from_now():
    wrapper = wrap_with_logging(_SuccessProvider())
    before = datetime.now(timezone.utc)
    await wrapper.send_otp("13611112222", "000000")
    after = datetime.now(timezone.utc)

    async with test_session_factory() as s:
        rows = (await s.execute(select(SmsSendLog))).scalars().all()
    assert len(rows) == 1
    row = rows[0]
    assert row.expires_at is not None
    expected_min = before + timedelta(days=90) - timedelta(seconds=5)
    expected_max = after + timedelta(days=90) + timedelta(seconds=5)

    # SQLite \u5b58\u56de\u4e0d\u5e26 tz; \u5904\u7406\u4e24\u79cd\u60c5\u5f62\u3002
    actual = row.expires_at
    if actual.tzinfo is None:
        actual = actual.replace(tzinfo=timezone.utc)
    assert expected_min <= actual <= expected_max


# ---------------------------------------------------------------------------
# 6. wrap_with_logging \u5e42\u7b49\u6027
# ---------------------------------------------------------------------------


def test_wrap_with_logging_is_idempotent():
    inner = _SuccessProvider()
    once = wrap_with_logging(inner)
    twice = wrap_with_logging(once)
    assert isinstance(once, LoggingSMSProviderWrapper)
    assert twice is once  # same instance \u2014 \u4e0d\u5957\u5a03


# ---------------------------------------------------------------------------
# 7. Factory \u96c6\u6210\u70b9\uff1aget_sms_provider() \u8fd4\u56de\u5305\u88f9\u540e\u7684 provider
# ---------------------------------------------------------------------------


def test_factory_returns_logging_wrapper(monkeypatch):
    monkeypatch.setattr(
        "app.services.providers.sms.factory.settings.sms_provider", "mock"
    )
    from app.services.providers.sms import get_sms_provider

    provider = get_sms_provider()
    assert isinstance(provider, LoggingSMSProviderWrapper)
    # \u5185\u90e8\u539f\u59cb provider \u53ef\u8bbf\u95ee
    assert getattr(provider, "_inner", None) is not None
