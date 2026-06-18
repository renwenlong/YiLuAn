"""[S3-OPS-BUDGET-CORE-REFACTOR-DRY] AI 预算 redis 原子操作公共核心.

背景
====

S2 ``ai_summary/budget.py`` (module-level API) 与 S3 ``ai_budget_guard.py``
(class + axis API) 各自实现了**相同语义**的 redis 原子操作 —
``incrbyfloat`` 预扣 / 超限回滚 / commit delta / release 退款 /
``get_today_spent`` 查询 / ``_daily_key`` 构造 + 36h TTL。两套代码逐字重复,
DRY 违反 (S3-DEV-002 implement 时为保 BC 选双轨, 留 tech debt)。

本模块抽取**纯 redis 原子层** (不含门限判定语义 / metric / 异常包装),
让 S2/S3 两侧 wrapper 各自包装自己的上层语义:
- S2: 超限 → 抛 ``BudgetExhausted``; 单档门限
- S3: 超限 → ``BudgetDecision.REJECT`` + alert; 3 档状态机 + Prom metric

设计边界
========

本模块**只管 redis 累加/查询的原子正确性**, 不做:
- 门限策略 (单档 vs 3 档) — 留给 wrapper
- metric / alert — 留给 wrapper (S3 有, S2 无)
- 异常类型 — 留给 wrapper (各自的 ``BudgetExhausted`` / ``BudgetCheckResult``)

Fail 语义
---------

redis 操作异常向上抛 ``BudgetCoreRedisError``, 由 wrapper 翻译成各自的
fail-closed 行为 (S2 ``BudgetExhausted(reason="redis_unavailable")`` /
S3 ``BudgetDecision.REJECT``)。``redis is None`` 的处理**留给 wrapper**
(两侧 None 语义略不同: S2 直接抛, S3 返 REJECT result), 本核心假设
传入的 redis 非 None。

Float drift note (IEEE 754)
---------------------------

``INCRBYFLOAT`` 内部 long double 累加有尾位漂移 (``49.99999999998``);
超限判定用 ``Decimal(str(...)) > limit``, 多出的 1e-12 永远 < ¥0.0001
最小可计费粒度, 不影响门限语义 (详见 S2 budget.py 模块 docstring)。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

logger = logging.getLogger("app.services._budget_core")

DEFAULT_DAILY_TTL_SECONDS = 36 * 3600  # 36h, 跨日 + 复盘窗口 (S2/S3 一致)


class BudgetCoreRedisError(Exception):
    """redis 原子操作失败. wrapper 捕获后翻译成各自的 fail-closed 行为."""


@dataclass(frozen=True)
class ReserveOutcome:
    """``check_and_reserve_impl`` 返回.

    Attributes
    ----------
    new_total:
        incrbyfloat 之后的当日累计 (若 ``exceeded`` 已回滚, 此值是**回滚前**
        的越界总额, 供 wrapper 算 usage / 填 metric)。
    exceeded:
        ``new_total > limit`` — 已在本函数内回滚预扣额。wrapper 据此走拒绝。
    """

    new_total: Decimal
    exceeded: bool


def daily_key(prefix: str, now: datetime | None = None) -> str:
    """构造当日 redis key: ``{prefix}:{YYYYMMDD}`` (UTC)."""
    now = now or datetime.now(timezone.utc)
    return f"{prefix}:{now.strftime('%Y%m%d')}"


async def check_and_reserve_impl(
    redis,
    key: str,
    amount: Decimal,
    limit: Decimal,
    *,
    ttl_seconds: int = DEFAULT_DAILY_TTL_SECONDS,
) -> ReserveOutcome:
    """原子预扣 ``amount`` 到 ``key`` 当日累计, 超 ``limit`` 则回滚.

    步骤:
    1. ``incrbyfloat(key, amount)`` 原子预扣 + ``expire(key, ttl)`` 刷新窗口
    2. 若 ``new_total > limit`` → 回滚预扣 (``incrbyfloat(key, -amount)``),
       返回 ``exceeded=True`` (wrapper 走拒绝)
    3. 否则返回 ``exceeded=False`` (wrapper 走允许 / 软门限判定)

    reserve-first 消除 TOCTOU: N 个并发各读 ``spent=49.95`` 都以为能花
    ¥0.05 的窗口被 incrbyfloat 原子性关闭。

    Raises
    ------
    BudgetCoreRedisError
        incrbyfloat / expire 异常 (wrapper 翻译成 fail-closed)。回滚自身的
        异常仅 warning log 不上抛 (best-effort, 不掩盖原始 reserve 成功语义)。
    """
    try:
        new_total_raw = await redis.incrbyfloat(key, float(amount))
        await redis.expire(key, ttl_seconds)
    except Exception as exc:
        logger.error("budget_core incrbyfloat failed key=%s: %s", key, exc)
        raise BudgetCoreRedisError(str(exc)) from exc

    new_total = Decimal(str(new_total_raw))
    if new_total > limit:
        # 回滚预扣, 让并发 caller 看到真实总额 + 单次越界不永久锁死当日剩余额度.
        try:
            await redis.incrbyfloat(key, float(-amount))
        except Exception as exc:
            logger.warning("budget_core rollback failed key=%s: %s", key, exc)
        return ReserveOutcome(new_total=new_total, exceeded=True)

    return ReserveOutcome(new_total=new_total, exceeded=False)


async def commit_impl(
    redis,
    key: str,
    actual: Decimal,
    reserved: Decimal,
) -> None:
    """调和 reserved vs actual 差额 (delta = actual - reserved).

    LLM 截断实际花更少 → delta<0 退款; 估算偏低 → delta>0 补扣; 相等 → no-op。
    delta 异常仅 warning (best-effort 对账, 不阻断主流程)。
    """
    delta = actual - reserved
    if delta == 0:
        return
    try:
        await redis.incrbyfloat(key, float(delta))
    except Exception as exc:
        logger.warning("budget_core commit delta failed key=%s: %s", key, exc)


async def release_impl(redis, key: str, reserved: Decimal) -> None:
    """退款已预扣的 ``reserved`` (LLM 调用失败后调). ``reserved==0`` no-op。"""
    if reserved == 0:
        return
    try:
        await redis.incrbyfloat(key, float(-reserved))
    except Exception as exc:
        logger.warning("budget_core release failed key=%s: %s", key, exc)


async def get_today_spent_impl(redis, key: str) -> Decimal:
    """查 ``key`` 当日累计花费 (含未 commit 的 reserve). 缺失 / 异常 → 0。"""
    try:
        raw = await redis.get(key)
    except Exception as exc:
        logger.warning("budget_core get_today_spent failed key=%s: %s", key, exc)
        return Decimal("0")
    if raw is None:
        return Decimal("0")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    return Decimal(str(raw))


__all__ = [
    "BudgetCoreRedisError",
    "DEFAULT_DAILY_TTL_SECONDS",
    "ReserveOutcome",
    "check_and_reserve_impl",
    "commit_impl",
    "daily_key",
    "get_today_spent_impl",
    "release_impl",
]
