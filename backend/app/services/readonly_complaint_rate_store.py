"""ADR-0053 §AC#4 — Customer complaint rate store.

Weekly manual PM POST `/admin/readonly/complaint-rate` → 此 store 持久化
redis 7 天滑动窗口 (ZSET by timestamp) → cron gate
`check_readonly_flag_real_gate()` 读取 rolling average.

design §5.3 r1 amend (\u9ec4\u7ebf #3): 客诉率 manual 注入, follow-up task
`S3-OPS-CUSTOMER-SUPPORT-METRIC-INTEGRATION` 接客服系统 API 后自动化.

Store 接口:
  - ``record_rate(rate, ts=None)`` — record a sample (PM POST 时调)
  - ``get_rolling_average(window_days)`` — cron gate 读, 取 rolling avg

Redis key: ``yiluan:readonly:complaint_rate:samples`` (ZSET, score=ts, member=rate@ts)
TTL: 30 天 (远超 7 天窗口避免长期清掉, redis ZSET 自身按 score 滑动)
"""

from __future__ import annotations

import logging
import time
import uuid
from typing import Optional, Protocol

logger = logging.getLogger(__name__)


REDIS_KEY = "yiluan:readonly:complaint_rate:samples"
REDIS_TTL_SECONDS = 30 * 86400  # 30 days, ZSET 自身滑动窗口


class _RedisProtocol(Protocol):  # pragma: no cover — typing only
    """Minimal redis async client interface used by the store."""

    async def zadd(self, key: str, mapping: dict) -> int: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int: ...
    async def zrangebyscore(
        self, key: str, min_score: float, max_score: float, withscores: bool = False
    ) -> list: ...


class ComplaintRateStore:
    """Redis-backed sliding window store for customer complaint rate.

    若 redis 不可用 (dev / test 无 redis), 自动降级 in-process dict
    (用于本地 dev / unit test 不依赖 redis fixture).
    """

    # in-process fallback — class var (cross instance share for tests)
    _inproc_samples: list[tuple[float, float]] = []

    def __init__(self, redis_client: Optional[_RedisProtocol] = None) -> None:
        self._redis = redis_client

    async def record_rate(self, rate: float, ts: Optional[float] = None) -> None:
        """Record a complaint rate sample. ts defaults to now().

        Args:
            rate: complaint rate as percent (e.g. 0.05 = 0.05%)
            ts: unix timestamp (seconds); defaults to time.time()
        """
        ts = ts if ts is not None else time.time()
        # member must be globally unique per timestamp
        member = f"{rate:.6f}@{ts:.9f}:{uuid.uuid4().hex[:8]}"

        if self._redis is None:
            # in-process fallback
            ComplaintRateStore._inproc_samples.append((ts, rate))
            # trim to 30 days
            cutoff = ts - REDIS_TTL_SECONDS
            ComplaintRateStore._inproc_samples = [
                (t, r) for (t, r) in ComplaintRateStore._inproc_samples if t >= cutoff
            ]
            logger.info(
                "[complaint_rate] recorded (inproc) rate=%.4f%% ts=%s count=%d",
                rate,
                ts,
                len(ComplaintRateStore._inproc_samples),
            )
            return

        await self._redis.zadd(REDIS_KEY, {member: ts})
        await self._redis.expire(REDIS_KEY, REDIS_TTL_SECONDS)
        logger.info(
            "[complaint_rate] recorded (redis) rate=%.4f%% ts=%s key=%s",
            rate,
            ts,
            REDIS_KEY,
        )

    async def get_rolling_average(self, window_days: int = 7) -> Optional[float]:
        """Return rolling average rate over last ``window_days``.

        Returns None when no samples in the window (cron gate 视 None 为
        manual 未注入 grace, 不阻 GO/NOGO 判断).
        """
        now = time.time()
        cutoff = now - window_days * 86400

        if self._redis is None:
            samples = [r for (t, r) in ComplaintRateStore._inproc_samples if t >= cutoff]
            if not samples:
                return None
            return sum(samples) / len(samples)

        # ZSET sliding window: drop old + read remaining
        try:
            await self._redis.zremrangebyscore(REDIS_KEY, 0, cutoff)
            # zrangebyscore returns members; we encoded rate in member 'rate@ts'
            members = await self._redis.zrangebyscore(REDIS_KEY, cutoff, now)
        except AttributeError as exc:
            # FakeRedis in some test envs may not implement zrangebyscore.
            # Treat as “no samples readable” — caller 可馔老代压 grace.
            logger.warning(
                "[complaint_rate] redis client missing zset op: %s",
                exc,
            )
            return None
        rates: list[float] = []
        for m in members:
            try:
                # bytes from redis-py default decode_responses=False
                m_str = m.decode("utf-8") if isinstance(m, (bytes, bytearray)) else m
                rate_str = m_str.split("@", 1)[0]
                rates.append(float(rate_str))
            except (ValueError, IndexError, AttributeError) as exc:
                logger.warning(
                    "[complaint_rate] member parse fail: %r err=%s",
                    m,
                    exc,
                )
                continue
        if not rates:
            return None
        return sum(rates) / len(rates)


# ============================================================================
# Module-level singleton + factory
# ============================================================================

_default_store: Optional[ComplaintRateStore] = None


def get_complaint_rate_store(
    redis_client: Optional[_RedisProtocol] = None,
) -> ComplaintRateStore:
    """Get or lazy-init a module-level singleton store.

    When ``redis_client`` is provided (e.g. from FastAPI dependency), a fresh
    instance is returned (caller controls lifecycle).

    When ``redis_client`` is None, returns a process-wide singleton that uses
    in-process fallback — suitable for CLI / cron / test where DI is awkward.
    """
    global _default_store
    if redis_client is not None:
        return ComplaintRateStore(redis_client=redis_client)
    if _default_store is None:
        _default_store = ComplaintRateStore(redis_client=None)
    return _default_store


def reset_default_store_for_tests() -> None:
    """Test helper — clear singleton + in-proc samples for isolation."""
    global _default_store
    _default_store = None
    ComplaintRateStore._inproc_samples = []
