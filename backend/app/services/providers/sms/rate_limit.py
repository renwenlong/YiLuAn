"""Per-phone rate limiter for SMS sends (P0-2).

Two windows enforced:

* **60 seconds**: at most 1 send per phone (anti-burst / anti-bot)
* **1 hour**: at most 5 sends per phone (daily-quota guard)

Backed by Redis when available; falls back to an in-process dict
(suitable for unit tests and single-worker dev). The fallback is NOT
safe across processes — production MUST run with Redis.

Limits are intentionally configurable through ``settings`` so ops can
loosen them during incidents without a code change:

* ``settings.sms_rate_limit_per_minute`` (default 1)
* ``settings.sms_rate_limit_per_hour`` (default 5)

(Defaults applied via ``getattr`` so adding the fields to
``Settings`` later is non-breaking.)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.config import settings

logger = logging.getLogger(__name__)


# In-process fallback store: {phone: [timestamp, timestamp, ...]}.
# Module-level on purpose so unit tests can clear it easily.
_inproc_store: dict[str, list[float]] = {}


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str = ""               # "ok" | "per_minute_exceeded" | "per_hour_exceeded"
    retry_after_seconds: int = 0   # hint for the caller / API response


def _per_minute_limit() -> int:
    return int(getattr(settings, "sms_rate_limit_per_minute", 1))


def _per_hour_limit() -> int:
    return int(getattr(settings, "sms_rate_limit_per_hour", 5))


class SMSRateLimiter:
    """Sliding-window rate limiter for SMS sends.

    Parameters
    ----------
    redis :
        Optional ``redis.asyncio.Redis`` client. When ``None``, the
        in-process fallback is used.
    """

    KEY_MINUTE = "sms:rate:minute:{phone}"
    KEY_HOUR_LIST = "sms:rate:hour:{phone}"

    def __init__(self, redis: Optional[Any] = None) -> None:
        self.redis = redis

    # --------------------------------------------------------------- API

    async def check_and_record(self, phone: str) -> RateLimitDecision:
        """Check both windows; on success record the new send timestamp."""
        per_min = _per_minute_limit()
        per_hour = _per_hour_limit()

        if self.redis is not None:
            return await self._redis_check(phone, per_min, per_hour)
        return self._inproc_check(phone, per_min, per_hour)

    # --------------------------------------------------------------- redis

    async def _redis_check(self, phone: str, per_min: int, per_hour: int) -> RateLimitDecision:
        minute_key = self.KEY_MINUTE.format(phone=phone)
        hour_key = self.KEY_HOUR_LIST.format(phone=phone)
        now = time.time()
        hour_cutoff = now - 3600

        # 60s window: simple SETNX-with-TTL counter.
        existing = await self.redis.get(minute_key)
        # Some redis libs return bytes, others str.
        if existing is not None:
            try:
                existing_int = int(existing)
            except (TypeError, ValueError):
                existing_int = per_min  # treat junk as "limit hit"
            if existing_int >= per_min:
                ttl = await self.redis.ttl(minute_key)
                ttl = max(int(ttl) if ttl is not None else 60, 1)
                logger.warning("[sms-rate] per-minute exceeded phone=<masked> ttl=%s", ttl)
                return RateLimitDecision(False, "per_minute_exceeded", ttl)

        # 1h window: ZSET of timestamps.
        await self.redis.zremrangebyscore(hour_key, 0, hour_cutoff)
        hour_count = await self.redis.zcard(hour_key)
        if hour_count is not None and int(hour_count) >= per_hour:
            logger.warning("[sms-rate] per-hour exceeded phone=<masked> count=%s", hour_count)
            return RateLimitDecision(False, "per_hour_exceeded", 3600)

        # Allowed — record the send.
        # 60s counter:
        new_val = await self.redis.incr(minute_key)
        if new_val == 1:
            await self.redis.expire(minute_key, 60)
        # Hour ZSET:
        # Member must be globally unique to avoid duplicate-suppression
        # in the underlying ZSET. Mix monotonic counter + uuid to be safe
        # against same-microsecond bursts.
        import uuid as _uuid
        member = f"{now:.9f}:{_uuid.uuid4().hex}"
        await self.redis.zadd(hour_key, {member: now})
        await self.redis.expire(hour_key, 3600)
        return RateLimitDecision(True, "ok", 0)

    # -------------------------------------------------------- in-process

    def _inproc_check(self, phone: str, per_min: int, per_hour: int) -> RateLimitDecision:
        now = time.time()
        bucket = _inproc_store.setdefault(phone, [])
        # Drop entries older than 1h.
        bucket[:] = [t for t in bucket if now - t < 3600]

        recent_minute = sum(1 for t in bucket if now - t < 60)
        if recent_minute >= per_min:
            oldest_in_min = min((t for t in bucket if now - t < 60), default=now)
            ttl = max(int(60 - (now - oldest_in_min)), 1)
            logger.warning("[sms-rate] per-minute exceeded (inproc) ttl=%s", ttl)
            return RateLimitDecision(False, "per_minute_exceeded", ttl)

        if len(bucket) >= per_hour:
            logger.warning("[sms-rate] per-hour exceeded (inproc) count=%s", len(bucket))
            return RateLimitDecision(False, "per_hour_exceeded", 3600)

        bucket.append(now)
        return RateLimitDecision(True, "ok", 0)


def reset_inproc_store() -> None:
    """Test helper — clears the in-process fallback store."""
    _inproc_store.clear()
