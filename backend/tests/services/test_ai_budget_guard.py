"""[S3-DEV-002] Tests for AIBudgetGuard multi-axis budget gatekeeper.

ADR-0048 §3 + AC#5 testing 要求:
- AC#5.1: axis 隔离 — S2_SUMMARY 花费不影响 S3_PREP 余额, 反之亦然
- AC#5.2: 3 档 threshold — NORMAL (0-89%) / WARN (90-99%) / EXHAUSTED (100%+)
- AC#5.3: cost 累计 — redis incrbyfloat 正确性 (浮点精度 + 回滚 + commit)
- AC#5.4: 跨 axis 隔离 (再校验): 同 instance 不接受 wrong axis 路由
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services.ai_budget_guard import (
    AIBudgetGuard,
    BudgetAxis,
    BudgetDecision,
    BudgetGuardConfigError,
)
from tests.services.test_ai_summary import _BudgetRedis  # 复用 fake redis fixture


@pytest.fixture
def redis():
    return _BudgetRedis()


@pytest.fixture
def now_fixed():
    return datetime(2026, 6, 9, 1, 30, 0, tzinfo=timezone.utc)


# ─────────────────────────── AC#5.1: axis 隔离 ───────────────────────────


@pytest.mark.asyncio
async def test_axis_isolation_s2_spending_does_not_affect_s3(redis, now_fixed):
    """S2_SUMMARY 花光预算后, S3_PREP 仍可正常调用 (key namespace 隔离)."""
    s2_guard = AIBudgetGuard(BudgetAxis.S2_SUMMARY)
    s3_guard = AIBudgetGuard(BudgetAxis.S3_PREP)

    # S2 接近用完: 49.99 / 50.0 = 99.98% (WARN 档但 ALLOW)
    s2_result = await s2_guard.check_and_reserve(
        redis,
        order_id="s2_order_1",
        estimated_cost_yuan=Decimal("0.049"),  # 单订单门限 0.05
        now=now_fixed,
    )
    assert s2_result.is_allowed
    # 直接 seed redis 到 50.0 = 100% (避免 1020 次循环慢)
    s2_key = s2_guard._daily_key(now_fixed)
    await redis.set(s2_key, "50.0")

    # S2 现在应该 EXHAUSTED (任何额外 reserve 都过 100%)
    s2_check = await s2_guard.check_and_reserve(
        redis,
        order_id="s2_order_after",
        estimated_cost_yuan=Decimal("0.049"),
        now=now_fixed,
    )
    assert s2_check.decision == BudgetDecision.REJECT

    # S3_PREP 仍 NORMAL (独立 redis key, 余额满)
    s3_result = await s3_guard.check_and_reserve(
        redis,
        order_id="s3_order_1",
        estimated_cost_yuan=Decimal("0.08"),
        now=now_fixed,
    )
    assert s3_result.decision == BudgetDecision.ALLOW
    assert s3_result.axis is BudgetAxis.S3_PREP

    # 验证 redis key 不重叠
    s2_key = s2_guard._daily_key(now_fixed)
    s3_key = s3_guard._daily_key(now_fixed)
    assert s2_key != s3_key
    assert "summary" in s2_key
    assert "s3_prep" in s3_key


@pytest.mark.asyncio
async def test_axis_redis_key_separate_namespaces(redis, now_fixed):
    """显式 verify s2 / s3 redis key 走不同 namespace."""
    s2_guard = AIBudgetGuard(BudgetAxis.S2_SUMMARY)
    s3_guard = AIBudgetGuard(BudgetAxis.S3_PREP)

    await s2_guard.check_and_reserve(
        redis, order_id="o1", estimated_cost_yuan=Decimal("0.01"), now=now_fixed
    )
    await s3_guard.check_and_reserve(
        redis, order_id="o2", estimated_cost_yuan=Decimal("0.05"), now=now_fixed
    )

    s2_spent = await s2_guard.get_today_spent(redis, now=now_fixed)
    s3_spent = await s3_guard.get_today_spent(redis, now=now_fixed)
    assert s2_spent == Decimal("0.01")
    assert s3_spent == Decimal("0.05")


# ──────────────────────── AC#5.2: 3 档 threshold ────────────────────────


@pytest.mark.asyncio
async def test_threshold_normal_below_90_pct_allow(redis, now_fixed):
    """0-89% NORMAL → ALLOW (无 alert)."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    # S3 daily budget = 100, 预扣 50 → 50% NORMAL
    await redis.incrbyfloat(guard._daily_key(now_fixed), 50.0)

    result = await guard.check_and_reserve(
        redis,
        order_id="o1",
        estimated_cost_yuan=Decimal("0.08"),
        now=now_fixed,
    )
    assert result.decision == BudgetDecision.ALLOW
    assert result.reservation_id is not None
    assert result.today_spent_after_reserve == Decimal("50.08")


@pytest.mark.asyncio
async def test_threshold_warn_90_to_99_pct_allow_with_alert(redis, now_fixed):
    """90-99% WARN → ALLOW (FALLBACK decision, 上层可选 template) + soft alert."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    # S3 daily budget = 100, 预扣 95 → 95% WARN
    await redis.incrbyfloat(guard._daily_key(now_fixed), 95.0)

    result = await guard.check_and_reserve(
        redis,
        order_id="o1",
        estimated_cost_yuan=Decimal("0.08"),
        now=now_fixed,
    )
    # FALLBACK = 软门限 + allowed
    assert result.decision == BudgetDecision.FALLBACK
    assert result.is_allowed  # FALLBACK 仍允许调用
    assert "soft warning" in result.reason.lower()


@pytest.mark.asyncio
async def test_threshold_exhausted_100_pct_reject_with_rollback(redis, now_fixed):
    """100%+ EXHAUSTED → REJECT + redis 预扣回滚 + warning alert."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    # S3 daily budget = 100, 已花 99.95 → 加 0.08 后 100.03 EXHAUSTED
    await redis.incrbyfloat(guard._daily_key(now_fixed), 99.95)

    result = await guard.check_and_reserve(
        redis,
        order_id="o1",
        estimated_cost_yuan=Decimal("0.08"),
        now=now_fixed,
    )
    assert result.decision == BudgetDecision.REJECT
    assert not result.is_allowed
    assert "exhausted" in result.reason.lower()

    # 验证 rollback: redis 应回到 99.95 (不是 100.03)
    spent_after_rollback = await guard.get_today_spent(redis, now=now_fixed)
    assert abs(float(spent_after_rollback) - 99.95) < 1e-6


# ──────────────────────── AC#5.3: cost 累计正确性 ────────────────────────


@pytest.mark.asyncio
async def test_cost_accumulation_incrbyfloat_correctness(redis, now_fixed):
    """多次 reserve + commit + release 后 redis 计数应 = sum of actual costs."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)

    # 调用 1: reserve 0.10, actual 0.08 → 应退 0.02
    r1 = await guard.check_and_reserve(
        redis, order_id="o1", estimated_cost_yuan=Decimal("0.10"), now=now_fixed,
    )
    assert r1.decision == BudgetDecision.ALLOW
    await guard.report_actual_cost(
        redis, r1.reservation_id,
        actual_cost_yuan=Decimal("0.08"),
        estimated_cost_yuan=Decimal("0.10"),
        now=now_fixed,
    )

    # 调用 2: reserve 0.10, LLM 失败 → release 全退
    r2 = await guard.check_and_reserve(
        redis, order_id="o2", estimated_cost_yuan=Decimal("0.10"), now=now_fixed,
    )
    assert r2.decision == BudgetDecision.ALLOW
    await guard.release(
        redis, r2.reservation_id, reserved_cost_yuan=Decimal("0.10"), now=now_fixed,
    )

    # 调用 3: reserve 0.10, actual 0.10 = estimate (无 delta)
    r3 = await guard.check_and_reserve(
        redis, order_id="o3", estimated_cost_yuan=Decimal("0.10"), now=now_fixed,
    )
    await guard.report_actual_cost(
        redis, r3.reservation_id,
        actual_cost_yuan=Decimal("0.10"),
        estimated_cost_yuan=Decimal("0.10"),
        now=now_fixed,
    )

    # 累计 应为 0.08 (R1 actual) + 0 (R2 released) + 0.10 (R3) = 0.18
    spent = await guard.get_today_spent(redis, now=now_fixed)
    # 浮点 tolerance
    assert abs(float(spent) - 0.18) < 1e-6


@pytest.mark.asyncio
async def test_cost_per_order_limit_returns_fallback(redis, now_fixed):
    """estimated cost > per-order 上限 → FALLBACK (不预扣 redis)."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    # S3 单订单 0.10, 试 0.20
    result = await guard.check_and_reserve(
        redis,
        order_id="o1",
        estimated_cost_yuan=Decimal("0.20"),
        now=now_fixed,
    )
    assert result.decision == BudgetDecision.FALLBACK
    assert "per-order limit" in result.reason
    # redis 应未变 (本次 0 预扣)
    spent = await guard.get_today_spent(redis, now=now_fixed)
    assert spent == Decimal("0")


@pytest.mark.asyncio
async def test_redis_unavailable_returns_reject_fail_closed(now_fixed):
    """redis=None → REJECT (fail-closed)."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    result = await guard.check_and_reserve(
        None,
        order_id="o1",
        estimated_cost_yuan=Decimal("0.05"),
        now=now_fixed,
    )
    assert result.decision == BudgetDecision.REJECT
    assert "redis_unavailable" in result.reason


# ──────────────────────── AC#5.4: enum + config ────────────────────────


def test_budget_axis_enum_values_stable():
    """BudgetAxis enum 字符串值不变 (避免 redis key migration)."""
    assert BudgetAxis.S2_SUMMARY.value == "s2_summary"
    assert BudgetAxis.S3_PREP.value == "s3_prep"


def test_axis_config_s2_uses_legacy_settings():
    """S2_SUMMARY 用老 settings 名 (零 BC break, AC#2)."""
    guard = AIBudgetGuard(BudgetAxis.S2_SUMMARY)
    # 默认 settings: ai_per_order=0.05, ai_daily=50.0
    assert guard.cost_per_order_yuan == Decimal("0.05")
    assert guard.daily_budget_yuan == Decimal("50.0")


def test_axis_config_s3_uses_new_settings():
    """S3_PREP 用新 settings (AC#3)."""
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    # 默认: s3_prep_cost=0.10, s3_prep_daily=100.0
    assert guard.cost_per_order_yuan == Decimal("0.10")
    assert guard.daily_budget_yuan == Decimal("100.0")


def test_config_error_when_per_order_exceeds_daily(monkeypatch):
    """单订单 cost > 日预算 → config error (永远 fallback, 不合理)."""
    from app.config import settings
    monkeypatch.setattr(settings, "s3_prep_cost_per_order_yuan", 200.0)
    monkeypatch.setattr(settings, "s3_prep_daily_budget_yuan", 100.0)
    with pytest.raises(BudgetGuardConfigError):
        AIBudgetGuard(BudgetAxis.S3_PREP)


def test_axis_disabled_returns_reject(monkeypatch, now_fixed):
    """settings.s3_prep_enabled = False → 始终 REJECT."""
    from app.config import settings
    monkeypatch.setattr(settings, "s3_prep_enabled", False)
    guard = AIBudgetGuard(BudgetAxis.S3_PREP)
    import asyncio

    result = asyncio.get_event_loop().run_until_complete(
        guard.check_and_reserve(
            None, order_id="o1",
            estimated_cost_yuan=Decimal("0.05"),
            now=now_fixed,
        )
    )
    assert result.decision == BudgetDecision.REJECT
    assert "disabled" in result.reason
