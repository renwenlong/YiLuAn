"""[S2-DEV-005] AI daily-budget gatekeeper (Redis-backed counter).

红线
----
- **日预算 ¥50 一刀切**：超限直接 ``BudgetExhausted`` → 调用方走模板降级，
  不发起 LLM 调用、不计费。
- **单订单 ¥0.05 上限**在 ``digester`` 层处理（需要 cost 估算后才截断），
  本模块只管「全平台累计 + 日级配额」。

Key 设计
--------
``ai:summary:daily_cost:{YYYYMMDD}``  -- Redis float-as-string，TTL 36h
（覆盖跨日缓冲 + 复盘窗口）。原子操作走 ``INCRBYFLOAT`` —— 多 worker
并发安全；不依赖外部 lock。

Fail-open vs fail-closed
------------------------
Redis 不可用时 **fail-closed** —— 拒绝继续调用 LLM。理由：金钱链路宁可
家属看到模板文案，也绝不让一次 Redis 故障让单日预算被几千个并发请求
打爆。``BudgetExhausted(reason="redis_unavailable")`` 由上游计入
``ai_summary_degraded_total{reason="daily_budget"}`` （归并降级原因，
不为这一种添新 reason，符合 PRD §F2 监控基线）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Final

from app.config import settings

logger = logging.getLogger("app.services.ai_summary.budget")

_DAILY_KEY_PREFIX: Final[str] = "ai:summary:daily_cost"
_DAILY_TTL_SECONDS: Final[int] = 36 * 3600  # 36h, 跨日 + 复盘缓冲


class BudgetExhausted(Exception):
    """Raised when the daily AI summary budget is (or would be) exceeded.

    Attributes
    ----------
    spent_yuan: Decimal
        Current accumulated spend for *today*.
    limit_yuan: Decimal
        The configured daily cap.
    reason: str
        Short token for metric labelling (``daily_budget`` / ``redis_unavailable``).
    """

    def __init__(self, *, spent_yuan: Decimal, limit_yuan: Decimal, reason: str = "daily_budget"):
        self.spent_yuan = spent_yuan
        self.limit_yuan = limit_yuan
        self.reason = reason
        super().__init__(
            f"AI daily budget exhausted (spent={spent_yuan} / limit={limit_yuan}, reason={reason})"
        )


def _daily_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{_DAILY_KEY_PREFIX}:{now.strftime('%Y%m%d')}"


async def check_and_reserve(redis, estimated_cost_yuan: Decimal, *, now: datetime | None = None) -> Decimal:
    """Optimistically reserve ``estimated_cost_yuan`` against today's budget.

    Returns the post-increment cumulative spend on success. Raises
    :class:`BudgetExhausted` if doing so would exceed
    ``settings.ai_daily_budget_yuan`` — in that case the increment is
    rolled back so the metric doesn't drift.

    Why reserve-first (vs charge-after-success)?
    - If the LLM call succeeds we commit; cost truth wins anyway.
    - If the LLM call fails after the reserve, we ``release`` to refund.
    - This shape eliminates the TOCTOU window where 10 concurrent calls
      each read ``spent=49.95`` and each decide they can spend ¥0.05.

    Redis errors → ``BudgetExhausted(reason="redis_unavailable")``
    (fail-closed; see module docstring).
    """
    limit = Decimal(str(settings.ai_daily_budget_yuan))
    key = _daily_key(now)

    if redis is None:
        raise BudgetExhausted(
            spent_yuan=Decimal("0"), limit_yuan=limit, reason="redis_unavailable"
        )

    try:
        new_total_raw = await redis.incrbyfloat(key, float(estimated_cost_yuan))
        # Best-effort TTL refresh; EXPIRE on every call is cheap and means
        # the key always has at least 36h horizon.
        await redis.expire(key, _DAILY_TTL_SECONDS)
    except Exception as exc:
        logger.error("AI budget redis error on incrbyfloat: %s", exc)
        raise BudgetExhausted(
            spent_yuan=Decimal("0"), limit_yuan=limit, reason="redis_unavailable"
        ) from exc

    new_total = Decimal(str(new_total_raw))
    if new_total > limit:
        # Roll back the reservation so concurrent callers see a truthful
        # total (and so a single overshoot doesn't permanently lock the
        # rest of the day at +cost-yuan above limit).
        try:
            await redis.incrbyfloat(key, float(-estimated_cost_yuan))
        except Exception as exc:
            logger.warning("AI budget rollback failed: %s", exc)
        raise BudgetExhausted(spent_yuan=new_total, limit_yuan=limit)

    return new_total


async def commit(redis, actual_cost_yuan: Decimal, reserved_cost_yuan: Decimal, *, now: datetime | None = None) -> None:
    """Reconcile reservation vs actual spend (delta = actual - reserved).

    If the LLM truncated and we ended up spending *less*, refund the
    difference so the daily counter stays honest.
    """
    if redis is None:
        return
    delta = actual_cost_yuan - reserved_cost_yuan
    if delta == 0:
        return
    try:
        await redis.incrbyfloat(_daily_key(now), float(delta))
    except Exception as exc:
        logger.warning("AI budget commit delta failed: %s", exc)


async def release(redis, reserved_cost_yuan: Decimal, *, now: datetime | None = None) -> None:
    """Refund a previously-reserved amount (call after LLM failure)."""
    if redis is None or reserved_cost_yuan == 0:
        return
    try:
        await redis.incrbyfloat(_daily_key(now), float(-reserved_cost_yuan))
    except Exception as exc:
        logger.warning("AI budget release failed: %s", exc)


async def get_today_spent(redis, *, now: datetime | None = None) -> Decimal:
    if redis is None:
        return Decimal("0")
    try:
        raw = await redis.get(_daily_key(now))
    except Exception as exc:
        logger.warning("AI budget get_today_spent failed: %s", exc)
        return Decimal("0")
    if raw is None:
        return Decimal("0")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return Decimal(str(raw))


__all__ = [
    "BudgetExhausted",
    "check_and_reserve",
    "commit",
    "get_today_spent",
    "release",
]
