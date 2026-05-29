"""[S2-DEV-011] Aliyun-SMS OTP verifier + 双轴频控 for the family-share
iOS/H5 fallback path (ADR-0036 §2.2 OTP 降级路径 + PRD-001 F2).

S2-DEV-002 留下的 OTP seam 当时是 "6 位数字即过" 的 trusted stub。这里
升级为真验证器:

1. ``send_otp`` — 双轴频控后生成 6 位码, 经 ``get_sms_provider()``
   (settings.sms_provider 决定 aliyun / mock) 下发, code 存 Redis (TTL 5min)。
   双轴红线 (魈+刻晴双 review):
     · 单 token / 24h ≤ 5 次发码          (链接泄露 → 防有人狂发轰炸)
     · 单手机号 / 1h ≤ 3 个不同 token 绑定 (号池滥用 → 防一个号刷多链接)
   超限抛 ``OtpRateLimitedError`` (上层转 429 + 人工客服文案)。

2. ``verify_otp`` — 取 Redis code 比对, 命中即删 (one-shot), 返回
   ``accessor`` = ``phone:{sha256(phone)[:16]}`` (真实手机号 hash, 替代
   stub 的 ``otp:{后2位}``)。失败按 reason 上报 ``share_otp_invalid_total``。

PII: 手机号绝不落明文 —— Redis key 用 sha256 hash, accessor 同。
Redis down → fail-closed (发码/验证都拒, 与 budget reserve 同语义)。
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from typing import Final

from redis.asyncio import Redis

from app.config import settings
from app.observability.share_metrics import (
    SHARE_OTP_INVALID_TOTAL,
    SHARE_OTP_SENT_TOTAL,
)
from app.services.providers.sms import get_sms_provider
from app.services.providers.sms.base import mask_phone_sms

logger = logging.getLogger(__name__)

# Redis key namespaces.
_CODE_KEY: Final[str] = "share:otp:code:{token}:{phash}"
_TOKEN_SEND_CNT_KEY: Final[str] = "share:otp:tokcnt:{token}"
_PHONE_TOKENS_KEY: Final[str] = "share:otp:phone:{phash}"

_TOKEN_DAILY_TTL: Final[int] = 24 * 60 * 60
_PHONE_WINDOW_TTL: Final[int] = 60 * 60


def _phone_hash(phone: str) -> str:
    return hashlib.sha256(phone.encode("utf-8")).hexdigest()[:16]


def accessor_for_phone(phone: str) -> str:
    """Stable, non-reversible accessor surrogate for a verified phone."""
    return f"phone:{_phone_hash(phone)}"


class OtpError(Exception):
    """Base for OTP-path failures (mapped to 4xx by the API layer)."""


class OtpRateLimitedError(OtpError):
    """双轴频控超限 — 转人工客服。"""


class OtpInvalidError(OtpError):
    """Code wrong / expired / not requested."""


class OtpSendError(OtpError):
    """Downstream SMS dispatch failed."""


class OtpService:
    """Redis-backed OTP issue + verify. Inject the request-scoped Redis."""

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    # -- issue -------------------------------------------------------------

    async def send_otp(self, *, token_value: str, phone: str) -> None:
        """Rate-limit (dual-axis) then dispatch a fresh OTP code.

        Raises OtpRateLimitedError / OtpSendError. Never logs raw phone.
        """
        phash = _phone_hash(phone)
        masked = mask_phone_sms(phone)

        await self._enforce_rate_limits(token_value=token_value, phash=phash)

        code = "".join(
            secrets.choice("0123456789")
            for _ in range(settings.share_otp_code_length)
        )

        provider = get_sms_provider()
        try:
            result = await provider.send_otp(phone=phone, code=code)
        except Exception as exc:  # outbound_call already classified/retried
            logger.error("[share-otp] SMS dispatch error phone=%s: %s", masked, exc)
            raise OtpSendError("OTP 发送失败，请稍后重试") from exc
        if not getattr(result, "ok", False):
            logger.error("[share-otp] SMS provider not-ok phone=%s", masked)
            raise OtpSendError("OTP 发送失败，请稍后重试")

        # Persist code + bump both counters only AFTER a successful send so a
        # failed dispatch never burns the user's quota.
        code_key = _CODE_KEY.format(token=token_value, phash=phash)
        await self._redis.set(code_key, code, ex=settings.share_otp_ttl_seconds)

        tok_cnt_key = _TOKEN_SEND_CNT_KEY.format(token=token_value)
        new_cnt = await self._redis.incr(tok_cnt_key)
        if new_cnt == 1:
            await self._redis.expire(tok_cnt_key, _TOKEN_DAILY_TTL)

        phone_tokens_key = _PHONE_TOKENS_KEY.format(phash=phash)
        await self._redis.sadd(phone_tokens_key, token_value)
        await self._redis.expire(phone_tokens_key, _PHONE_WINDOW_TTL)

        SHARE_OTP_SENT_TOTAL.inc()
        logger.info("[share-otp] sent phone=%s token=%s", masked, token_value[:8])

    async def _enforce_rate_limits(self, *, token_value: str, phash: str) -> None:
        # Axis 1: single token / 24h ≤ N sends.
        tok_cnt_key = _TOKEN_SEND_CNT_KEY.format(token=token_value)
        sent = int(await self._redis.get(tok_cnt_key) or 0)
        if sent >= settings.share_otp_token_daily_cap:
            SHARE_OTP_INVALID_TOTAL.labels(reason="rate_limited").inc()
            raise OtpRateLimitedError(
                "该分享链接今日验证码发送次数过多，请联系陪诊客服"
            )

        # Axis 2: single phone / 1h ≤ N distinct tokens bound.
        phone_tokens_key = _PHONE_TOKENS_KEY.format(phash=phash)
        bound = await self._redis.smembers(phone_tokens_key)
        # Adding *this* token only counts if it's new.
        if token_value not in bound and (
            len(bound) >= settings.share_otp_phone_token_cap
        ):
            SHARE_OTP_INVALID_TOTAL.labels(reason="rate_limited").inc()
            raise OtpRateLimitedError(
                "该手机号短时间内绑定的分享链接过多，请联系陪诊客服"
            )

    # -- verify ------------------------------------------------------------

    async def verify_otp(self, *, token_value: str, phone: str, code: str) -> str:
        """Verify a submitted code; return the phone-based accessor on hit.

        Raises OtpInvalidError on wrong/expired/never-requested. One-shot:
        a correct code is consumed so it can't be replayed.
        """
        phash = _phone_hash(phone)
        code_key = _CODE_KEY.format(token=token_value, phash=phash)

        stored = await self._redis.get(code_key)
        if stored is None:
            # Either never requested or TTL-expired — indistinguishable on
            # purpose (don't leak which). Bucket as expired.
            SHARE_OTP_INVALID_TOTAL.labels(reason="expired").inc()
            raise OtpInvalidError("验证码已过期或未发送，请重新获取")

        if not secrets.compare_digest(str(stored), str(code)):
            SHARE_OTP_INVALID_TOTAL.labels(reason="wrong_code").inc()
            raise OtpInvalidError("验证码错误")

        # Correct — consume (one-shot) and hand back the stable accessor.
        await self._redis.delete(code_key)
        return accessor_for_phone(phone)
