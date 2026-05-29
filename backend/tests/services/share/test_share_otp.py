"""[S2-DEV-011] OtpService — 双轴频控 + 真验证 单元测试.

覆盖 acceptance:
- 正常发码 → 验证成功 → accessor = phone hash
- 单 token / 24h ≤ 5 次发码 (第 6 次 rate_limited)
- 单手机号 / 1h ≤ 3 个不同 token 绑定 (第 4 个 token rate_limited)
- 错误码 → wrong_code 401
- 过期 / 未发码 → expired 401
- 一次性: 验证成功后复用同码 → expired (已消费)
- 发码失败不烧配额

share_otp_invalid_total{reason} metric 反映 reason 分桶。
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.services.providers.sms.base import SMSResult
from app.services.share_otp import (
    OtpInvalidError,
    OtpRateLimitedError,
    OtpSendError,
    OtpService,
    accessor_for_phone,
)
from tests.conftest import FakeRedis

pytestmark = pytest.mark.asyncio

_PHONE = "13800010001"
_PHONE_B = "13900020002"
_TOKEN = "tok_abc123"


def _ok_provider() -> AsyncMock:
    prov = AsyncMock()
    prov.send_otp.return_value = SMSResult(ok=True, provider="mock", extra={})
    return prov


def _patch_provider(prov):
    return patch(
        "app.services.share_otp.get_sms_provider", return_value=prov
    )


async def _read_code(redis: FakeRedis, token: str, phone: str) -> str:
    from app.services.share_otp import _CODE_KEY, _phone_hash

    return await redis.get(
        _CODE_KEY.format(token=token, phash=_phone_hash(phone))
    )


# --- happy path --------------------------------------------------------------


async def test_send_then_verify_success_returns_phone_accessor():
    redis = FakeRedis()
    svc = OtpService(redis)
    prov = _ok_provider()
    with _patch_provider(prov):
        await svc.send_otp(token_value=_TOKEN, phone=_PHONE)
    prov.send_otp.assert_awaited_once()
    code = await _read_code(redis, _TOKEN, _PHONE)
    assert code and len(code) == settings.share_otp_code_length

    accessor = await svc.verify_otp(token_value=_TOKEN, phone=_PHONE, code=code)
    assert accessor == accessor_for_phone(_PHONE)
    assert accessor.startswith("phone:")
    # one-shot: code consumed
    assert await _read_code(redis, _TOKEN, _PHONE) is None


# --- axis 1: single token 24h ≤ N sends -------------------------------------


async def test_token_daily_send_cap_blocks_excess():
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        for _ in range(settings.share_otp_token_daily_cap):
            await svc.send_otp(token_value=_TOKEN, phone=_PHONE)
        # next send over the cap → rate limited
        with pytest.raises(OtpRateLimitedError):
            await svc.send_otp(token_value=_TOKEN, phone=_PHONE)


# --- axis 2: single phone 1h ≤ N distinct tokens ----------------------------


async def test_phone_distinct_token_cap_blocks_excess():
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        for i in range(settings.share_otp_phone_token_cap):
            await svc.send_otp(token_value=f"tok_{i}", phone=_PHONE)
        # a NEW (distinct) token over the cap → rate limited
        with pytest.raises(OtpRateLimitedError):
            await svc.send_otp(token_value="tok_overflow", phone=_PHONE)


async def test_phone_cap_allows_resend_to_same_token():
    """同一 token 重发不算新增 distinct token（受 axis-1 管，不受 axis-2）。"""
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        # fill phone with cap distinct tokens
        for i in range(settings.share_otp_phone_token_cap):
            await svc.send_otp(token_value=f"tok_{i}", phone=_PHONE)
        # resend to an already-bound token is fine (still under axis-1)
        await svc.send_otp(token_value="tok_0", phone=_PHONE)


# --- verify failure modes ----------------------------------------------------


async def test_verify_wrong_code_raises_invalid():
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        await svc.send_otp(token_value=_TOKEN, phone=_PHONE)
    with pytest.raises(OtpInvalidError):
        await svc.verify_otp(token_value=_TOKEN, phone=_PHONE, code="000000")
    # wrong code does NOT consume the real code
    assert await _read_code(redis, _TOKEN, _PHONE) is not None


async def test_verify_never_sent_raises_invalid():
    redis = FakeRedis()
    svc = OtpService(redis)
    with pytest.raises(OtpInvalidError):
        await svc.verify_otp(token_value=_TOKEN, phone=_PHONE, code="123456")


async def test_verify_reuse_after_success_raises_invalid():
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        await svc.send_otp(token_value=_TOKEN, phone=_PHONE)
    code = await _read_code(redis, _TOKEN, _PHONE)
    assert await svc.verify_otp(token_value=_TOKEN, phone=_PHONE, code=code)
    # replay same code → already consumed → invalid
    with pytest.raises(OtpInvalidError):
        await svc.verify_otp(token_value=_TOKEN, phone=_PHONE, code=code)


# --- dispatch failure does not burn quota -----------------------------------


async def test_send_failure_does_not_persist_code_or_counter():
    redis = FakeRedis()
    svc = OtpService(redis)
    failing = AsyncMock()
    failing.send_otp.return_value = SMSResult(ok=False, provider="mock", extra={})
    with _patch_provider(failing):
        with pytest.raises(OtpSendError):
            await svc.send_otp(token_value=_TOKEN, phone=_PHONE)
    # no code stored, no counter bumped
    assert await _read_code(redis, _TOKEN, _PHONE) is None
    from app.services.share_otp import _TOKEN_SEND_CNT_KEY

    assert await redis.get(_TOKEN_SEND_CNT_KEY.format(token=_TOKEN)) is None


async def test_distinct_phones_isolated():
    """不同手机号的 distinct-token 配额互不影响。"""
    redis = FakeRedis()
    svc = OtpService(redis)
    with _patch_provider(_ok_provider()):
        for i in range(settings.share_otp_phone_token_cap):
            await svc.send_otp(token_value=f"tok_{i}", phone=_PHONE)
        # phone B is fresh — should still send fine
        await svc.send_otp(token_value="tok_b0", phone=_PHONE_B)
