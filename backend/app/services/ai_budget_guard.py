"""[S3-DEV-002] AIBudgetGuard — 多 axis AI 预算 gatekeeper (ADR-0048 §3).

设计宗旨
========

ADR-0048 §3 字面: BudgetAxis enum 隔离 (S2_SUMMARY / S3_PREP / 未来), AIBudgetGuard
通用类按 axis 路由配置 + redis key + metric label, **不允许跨 axis budget 互调**.

3 档 fallback 状态机
-----------------

| 日预算使用率 | 状态        | 决策                                              |
|--------------|-------------|---------------------------------------------------|
| 0-89%        | NORMAL      | ``ALLOW`` — 正常调用 LLM                         |
| 90-99%       | WARN        | ``ALLOW`` + fire ``ai_budget_soft_warning`` info |
| 100%+        | EXHAUSTED   | ``REJECT`` + fire ``ai_budget_exhausted`` warning |
|              |             | + fallback template                               |

与 S2 ``ai_summary/budget.py`` 的关系
----------------------------------

S2 老路径 (``digester.py`` 用 ``from app.services.ai_summary import budget``)
**保留不动**, 真源 ``ai_per_order_budget_yuan`` / ``ai_daily_budget_yuan`` 不改名
(零 BC break, ADR §3 + AC#2).

**新功能 (S3 准备包) 走本模块** ``AIBudgetGuard(BudgetAxis.S3_PREP)``,
未来 S2 调用方可平滑迁移 ``AIBudgetGuard(BudgetAxis.S2_SUMMARY)`` (行为等价,
metric label 不同 → grafana 看板更细).

Redis key 隔离
-------------

每 axis 独立 namespace:
- S2_SUMMARY: ``ai:summary:daily_cost:{YYYYMMDD}`` (兼 S2 老 key, 同 namespace)
- S3_PREP:    ``ai:budget:s3_prep:daily_cost:{YYYYMMDD}``

axis 之间 redis key 不重叠, **隔离保证 = key namespace 隔离 + AIBudgetGuard
class 按 axis 实例化**.

Fail-closed 语义
---------------

Redis 不可用 → ``REJECT`` (fail-closed). 理由同 S2 ``ai_summary/budget.py``:
金钱链路宁可家属看 template 也不让单次 Redis 故障让日预算被打爆。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from app.config import settings
from app.observability.ai_budget_metrics import (
    AI_BUDGET_CHECK_TOTAL,
    AI_BUDGET_COMMITTED_CNY_TOTAL,
    AI_BUDGET_RESERVED_CNY_TOTAL,
    AI_BUDGET_THRESHOLD_ALERTS_TOTAL,
)

logger = logging.getLogger("app.services.ai_budget_guard")


# ─────────────────────────── BudgetAxis enum ───────────────────────────


class BudgetAxis(str, Enum):
    """每个 AI 用途一条 axis. 新增 axis 必须同步更新 ``_AXIS_CONFIG``."""

    S2_SUMMARY = "s2_summary"
    S3_PREP = "s3_prep"


@dataclass(frozen=True)
class _AxisConfig:
    """Axis 配置: cost limit + daily budget + redis key prefix."""

    cost_per_order_yuan: Decimal
    daily_budget_yuan: Decimal
    redis_key_prefix: str  # 形如 "ai:summary:daily_cost" / "ai:budget:s3_prep:daily_cost"
    enabled: bool
    soft_threshold_pct: int  # 90 = 90% 触 soft warn


def _load_axis_config(axis: BudgetAxis) -> _AxisConfig:
    """从 settings 取 axis 对应配置. 单点路由, 防止跨 axis 误配。"""
    if axis is BudgetAxis.S2_SUMMARY:
        return _AxisConfig(
            cost_per_order_yuan=Decimal(str(settings.ai_per_order_budget_yuan)),
            daily_budget_yuan=Decimal(str(settings.ai_daily_budget_yuan)),
            redis_key_prefix="ai:summary:daily_cost",  # 与 S2 老 key 同 namespace
            enabled=True,  # S2 状态拼: 老 budget.py 无 enable flag, 总是 enabled
            soft_threshold_pct=90,  # S2 默认 90%, 未来可加 settings
        )
    if axis is BudgetAxis.S3_PREP:
        return _AxisConfig(
            cost_per_order_yuan=Decimal(str(settings.s3_prep_cost_per_order_yuan)),
            daily_budget_yuan=Decimal(str(settings.s3_prep_daily_budget_yuan)),
            redis_key_prefix="ai:budget:s3_prep:daily_cost",
            enabled=settings.s3_prep_enabled,
            soft_threshold_pct=settings.s3_prep_fallback_threshold_pct,
        )
    raise ValueError(f"Unknown BudgetAxis: {axis!r}")


# ─────────────────────────── Result types ───────────────────────────


class BudgetDecision(str, Enum):
    """check_and_reserve 决策 (3 档 fallback 状态机)."""

    ALLOW = "allow"          # NORMAL 0-89%
    FALLBACK = "fallback"    # WARN 90-99% (仍 allow + alert) / 单订单超
    REJECT = "reject"        # EXHAUSTED 100%+ / redis 不可用


@dataclass(frozen=True)
class BudgetCheckResult:
    """check_and_reserve 返回."""

    decision: BudgetDecision
    axis: BudgetAxis
    estimated_cost_yuan: Decimal
    reservation_id: Optional[UUID] = None  # 仅 ALLOW + FALLBACK (允许调用) 时填
    reason: str = ""
    today_spent_after_reserve: Decimal = Decimal("0")  # 含本次 reserve 之后日累计

    @property
    def is_allowed(self) -> bool:
        """调用方据此决定是否真发 LLM call (ALLOW + FALLBACK = 允许)."""
        return self.decision in (BudgetDecision.ALLOW, BudgetDecision.FALLBACK)


class BudgetGuardConfigError(Exception):
    """settings 配置非法 (如 cost > daily budget)."""


_DAILY_TTL_SECONDS = 36 * 3600  # 36h, 跨日 + 复盘窗口 (同 S2)


# ─────────────────────────── AIBudgetGuard ───────────────────────────


class AIBudgetGuard:
    """Per-axis AI budget gatekeeper.

    Usage::

        guard = AIBudgetGuard(BudgetAxis.S3_PREP)
        result = await guard.check_and_reserve(
            redis_client, order_id="ord_123", estimated_cost_yuan=Decimal("0.08")
        )
        if not result.is_allowed:
            return template_fallback()
        try:
            actual = await call_llm()
            await guard.report_actual_cost(redis_client, result.reservation_id,
                                            actual_cost_yuan=actual.cost,
                                            estimated_cost_yuan=result.estimated_cost_yuan)
        except Exception:
            await guard.release(redis_client, result.reservation_id,
                                 reserved_cost_yuan=result.estimated_cost_yuan)
            raise
    """

    def __init__(self, axis: BudgetAxis):
        self.axis = axis
        self._cfg = _load_axis_config(axis)
        # Sanity check: 单订单 cost 不应 > 日预算 (会永远 fallback).
        if self._cfg.cost_per_order_yuan > self._cfg.daily_budget_yuan:
            raise BudgetGuardConfigError(
                f"axis={axis.value} per-order cost ¥{self._cfg.cost_per_order_yuan} "
                f"exceeds daily budget ¥{self._cfg.daily_budget_yuan}"
            )

    # ----- helper -----

    def _daily_key(self, now: datetime | None = None) -> str:
        now = now or datetime.now(timezone.utc)
        return f"{self._cfg.redis_key_prefix}:{now.strftime('%Y%m%d')}"

    def _record_check(self, result: BudgetDecision) -> None:
        AI_BUDGET_CHECK_TOTAL.labels(axis=self.axis.value, result=result.value).inc()

    def _fire_alert(self, severity: str) -> None:
        """Prom counter 增计, 由 alertmanager rule 监听该 counter rate 触发实际通知.

        severity ∈ ``info`` (软门限 90%) / ``warning`` (硬门限 100%+).
        无需 backend 直接 POST webhook — 走 Prom-native 路径 (零新依赖,
        ADR-0048 §3 决策 2 自拍 a).
        """
        AI_BUDGET_THRESHOLD_ALERTS_TOTAL.labels(
            axis=self.axis.value, severity=severity
        ).inc()
        logger.warning(
            "AI budget threshold reached: axis=%s severity=%s",
            self.axis.value, severity,
        )

    # ----- public API -----

    async def check_and_reserve(
        self,
        redis,
        *,
        order_id: str,
        estimated_cost_yuan: Decimal,
        now: datetime | None = None,
    ) -> BudgetCheckResult:
        """Optimistically reserve ``estimated_cost_yuan`` against today's axis budget.

        返回 3 档:
        - ``ALLOW``  (0-89%, NORMAL)            — 已预扣, 调用方可继续 LLM
        - ``FALLBACK`` (90-99% WARN, 或单订单超) — 仍允许 + fire info alert,
          上层可选择走 template (ADR 不强制, 见调用方语义)
        - ``REJECT`` (100%+ EXHAUSTED, 或 redis 不可用) — 拒绝, 不预扣, 强制 fallback

        Idempotency: ``order_id`` 当前**不参与去重** (与 S2 ``ai_summary/budget.py``
        同) — 由上游业务确保不重复调 (chunkqueue worker 一次只投一次).
        """
        if not self._cfg.enabled:
            return BudgetCheckResult(
                decision=BudgetDecision.REJECT,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reason="axis disabled in settings",
            )

        # 1. 单订单门限 (优先 — 永远不会过单订单上限发起调用)
        if estimated_cost_yuan > self._cfg.cost_per_order_yuan:
            self._record_check(BudgetDecision.FALLBACK)
            return BudgetCheckResult(
                decision=BudgetDecision.FALLBACK,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reason=(
                    f"estimated cost ¥{estimated_cost_yuan} > per-order limit "
                    f"¥{self._cfg.cost_per_order_yuan} → fallback template"
                ),
            )

        # 2. Redis 不可用 → fail-closed REJECT
        if redis is None:
            self._record_check(BudgetDecision.REJECT)
            return BudgetCheckResult(
                decision=BudgetDecision.REJECT,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reason="redis_unavailable",
            )

        # 3. 日预算门限 — 原子预扣 (incrbyfloat)
        key = self._daily_key(now)
        try:
            new_total_raw = await redis.incrbyfloat(key, float(estimated_cost_yuan))
            await redis.expire(key, _DAILY_TTL_SECONDS)
        except Exception as exc:
            logger.error("AI budget redis incrbyfloat failed axis=%s: %s",
                         self.axis.value, exc)
            self._record_check(BudgetDecision.REJECT)
            return BudgetCheckResult(
                decision=BudgetDecision.REJECT,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reason=f"redis_unavailable: {exc}",
            )

        new_total = Decimal(str(new_total_raw))
        usage_pct = float(new_total / self._cfg.daily_budget_yuan * 100)

        # 100%+ → 回滚 + EXHAUSTED reject + warning alert
        if new_total > self._cfg.daily_budget_yuan:
            try:
                await redis.incrbyfloat(key, float(-estimated_cost_yuan))
            except Exception as exc:
                logger.warning("AI budget rollback failed axis=%s: %s",
                               self.axis.value, exc)
            self._fire_alert("warning")
            self._record_check(BudgetDecision.REJECT)
            return BudgetCheckResult(
                decision=BudgetDecision.REJECT,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reason=(
                    f"daily budget exhausted: ¥{new_total} > "
                    f"¥{self._cfg.daily_budget_yuan} (axis={self.axis.value})"
                ),
                today_spent_after_reserve=new_total - estimated_cost_yuan,
            )

        # 90-99% → ALLOW + 软门限 info alert
        if usage_pct >= self._cfg.soft_threshold_pct:
            self._fire_alert("info")
            AI_BUDGET_RESERVED_CNY_TOTAL.labels(axis=self.axis.value).inc(
                float(estimated_cost_yuan)
            )
            self._record_check(BudgetDecision.FALLBACK)
            return BudgetCheckResult(
                decision=BudgetDecision.FALLBACK,
                axis=self.axis,
                estimated_cost_yuan=estimated_cost_yuan,
                reservation_id=uuid4(),
                reason=(
                    f"daily budget soft warning: ¥{new_total} / "
                    f"¥{self._cfg.daily_budget_yuan} ({usage_pct:.1f}%)"
                ),
                today_spent_after_reserve=new_total,
            )

        # 0-89% NORMAL → ALLOW
        AI_BUDGET_RESERVED_CNY_TOTAL.labels(axis=self.axis.value).inc(
            float(estimated_cost_yuan)
        )
        self._record_check(BudgetDecision.ALLOW)
        return BudgetCheckResult(
            decision=BudgetDecision.ALLOW,
            axis=self.axis,
            estimated_cost_yuan=estimated_cost_yuan,
            reservation_id=uuid4(),
            today_spent_after_reserve=new_total,
        )

    async def report_actual_cost(
        self,
        redis,
        reservation_id: UUID | None,
        *,
        actual_cost_yuan: Decimal,
        estimated_cost_yuan: Decimal,
        now: datetime | None = None,
    ) -> None:
        """LLM 调用完成后回补 actual vs estimated 的差额 (可正可负).

        delta = actual - estimated:
        - actual < estimated (LLM 截断, 实际花少) → 退款 (delta < 0, redis 减)
        - actual > estimated (估算偏低) → 补扣 (delta > 0, redis 加)
        - actual == estimated → 无操作

        ``reservation_id`` 当前**不做幂等**, 由调用方确保 reserve/commit 配对调
        (与 S2 同).
        """
        if redis is None:
            return
        delta = actual_cost_yuan - estimated_cost_yuan
        AI_BUDGET_COMMITTED_CNY_TOTAL.labels(axis=self.axis.value).inc(
            float(actual_cost_yuan)
        )
        if delta == 0:
            return
        try:
            await redis.incrbyfloat(self._daily_key(now), float(delta))
        except Exception as exc:
            logger.warning(
                "AI budget report_actual_cost delta failed axis=%s: %s",
                self.axis.value, exc,
            )

    async def release(
        self,
        redis,
        reservation_id: UUID | None,
        *,
        reserved_cost_yuan: Decimal,
        now: datetime | None = None,
    ) -> None:
        """LLM 调用失败后退款已预扣的 ``reserved_cost_yuan``."""
        if redis is None or reserved_cost_yuan == 0:
            return
        try:
            await redis.incrbyfloat(self._daily_key(now), float(-reserved_cost_yuan))
        except Exception as exc:
            logger.warning("AI budget release failed axis=%s: %s",
                           self.axis.value, exc)

    async def get_today_spent(
        self, redis, *, now: datetime | None = None
    ) -> Decimal:
        """查询本 axis 今日已累计花费 (含未 commit 的 reserve)."""
        if redis is None:
            return Decimal("0")
        try:
            raw = await redis.get(self._daily_key(now))
        except Exception as exc:
            logger.warning("AI budget get_today_spent failed axis=%s: %s",
                           self.axis.value, exc)
            return Decimal("0")
        if raw is None:
            return Decimal("0")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return Decimal(str(raw))

    @property
    def daily_budget_yuan(self) -> Decimal:
        """暴露当前 axis 日预算上限 (admin 查询用)."""
        return self._cfg.daily_budget_yuan

    @property
    def cost_per_order_yuan(self) -> Decimal:
        """暴露当前 axis 单订单上限."""
        return self._cfg.cost_per_order_yuan


__all__ = [
    "AIBudgetGuard",
    "BudgetAxis",
    "BudgetCheckResult",
    "BudgetDecision",
    "BudgetGuardConfigError",
]
