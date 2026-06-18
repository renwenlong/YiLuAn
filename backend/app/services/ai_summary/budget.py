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

Float drift note (IEEE 754)
---------------------------
``INCRBYFLOAT`` 在 Redis 内部用 long double 存累计值，跨 N 次小额累加
会出现尾位漂移（典型表现：``spent=49.99999999998`` 而非 ``50``）。SRE
看监控时不要惊慌——超限判定用的是 ``Decimal(str(...)) > limit``，多
出来的 1e-12 永远 < ¥0.0001 的最小可计费粒度，不影响门限语义；如果
需要精确审计请走每日跑批从 ``ai_summary_cost_cny_total`` Prom 抽样
汇总（那条是 ``inc(float(Decimal))``，无累加漂移）。
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from typing import Final

from app.config import settings
from app.services import _budget_core

logger = logging.getLogger("app.services.ai_summary.budget")

_DAILY_KEY_PREFIX: Final[str] = "ai:summary:daily_cost"
# 36h TTL 现由 _budget_core.DEFAULT_DAILY_TTL_SECONDS 提供 (S2/S3 一致)。
_DAILY_TTL_SECONDS: Final[int] = _budget_core.DEFAULT_DAILY_TTL_SECONDS


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
    return _budget_core.daily_key(_DAILY_KEY_PREFIX, now)


async def check_and_reserve(
    redis, estimated_cost_yuan: Decimal, *, now: datetime | None = None
) -> Decimal:
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
        raise BudgetExhausted(spent_yuan=Decimal("0"), limit_yuan=limit, reason="redis_unavailable")

    try:
        outcome = await _budget_core.check_and_reserve_impl(
            redis, key, estimated_cost_yuan, limit, ttl_seconds=_DAILY_TTL_SECONDS
        )
    except _budget_core.BudgetCoreRedisError as exc:
        # fail-closed: 一次 redis 故障不让日预算被几千并发打爆。
        raise BudgetExhausted(
            spent_yuan=Decimal("0"), limit_yuan=limit, reason="redis_unavailable"
        ) from exc

    if outcome.exceeded:
        # impl 已回滚预扣; new_total 是越界前总额 (供调用方看真实超出多少)。
        raise BudgetExhausted(spent_yuan=outcome.new_total, limit_yuan=limit)

    return outcome.new_total


async def commit(
    redis, actual_cost_yuan: Decimal, reserved_cost_yuan: Decimal, *, now: datetime | None = None
) -> None:
    """Reconcile reservation vs actual spend (delta = actual - reserved).

    If the LLM truncated and we ended up spending *less*, refund the
    difference so the daily counter stays honest.
    """
    if redis is None:
        return
    await _budget_core.commit_impl(redis, _daily_key(now), actual_cost_yuan, reserved_cost_yuan)


async def release(redis, reserved_cost_yuan: Decimal, *, now: datetime | None = None) -> None:
    """Refund a previously-reserved amount (call after LLM failure)."""
    if redis is None or reserved_cost_yuan == 0:
        return
    await _budget_core.release_impl(redis, _daily_key(now), reserved_cost_yuan)


async def get_today_spent(redis, *, now: datetime | None = None) -> Decimal:
    if redis is None:
        return Decimal("0")
    return await _budget_core.get_today_spent_impl(redis, _daily_key(now))


__all__ = [
    "BudgetExhausted",
    "check_and_reserve",
    "commit",
    "get_today_spent",
    "release",
]
