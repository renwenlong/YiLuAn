"""[S3-OPS-BUDGET-CORE-REFACTOR-DRY] Tests for _budget_core redis 原子层.

acceptance 4 类 forward 正确性:
- check_and_reserve_impl: 预扣 / 超限回滚 / redis 异常
- commit_impl: delta 正/负/零
- release_impl: 退款 / 零额 no-op
- get_today_spent_impl: 读取 / 缺失 / bytes decode
+ daily_key 格式
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.services import _budget_core
from tests.services.test_ai_summary import _BudgetRedis


@pytest.fixture
def redis():
    return _BudgetRedis()


@pytest.fixture
def now_fixed():
    return datetime(2026, 6, 17, 1, 30, 0, tzinfo=timezone.utc)


class _BoomRedis(_BudgetRedis):
    """incrbyfloat 抛异常, 验证 fail path."""

    async def incrbyfloat(self, key: str, amount: float) -> float:
        raise RuntimeError("redis down")


# ─────────────────────── daily_key ───────────────────────


def test_daily_key_format(now_fixed):
    assert _budget_core.daily_key("ai:summary:daily_cost", now_fixed) == (
        "ai:summary:daily_cost:20260617"
    )


def test_daily_key_defaults_to_utc_now():
    key = _budget_core.daily_key("p")
    # 形如 p:YYYYMMDD
    assert key.startswith("p:")
    assert len(key.split(":")[1]) == 8


# ─────────────────── check_and_reserve_impl ───────────────────


@pytest.mark.asyncio
async def test_check_and_reserve_normal(redis, now_fixed):
    """未超限: 返回 new_total + exceeded=False, redis 累计正确."""
    key = _budget_core.daily_key("p", now_fixed)
    outcome = await _budget_core.check_and_reserve_impl(
        redis, key, Decimal("10"), Decimal("50")
    )
    assert outcome.exceeded is False
    assert outcome.new_total == Decimal("10.0")
    # redis 真累计了
    assert Decimal(str(await redis.get(key))) == Decimal("10.0")


@pytest.mark.asyncio
async def test_check_and_reserve_accumulates(redis, now_fixed):
    """多次预扣累加."""
    key = _budget_core.daily_key("p", now_fixed)
    await _budget_core.check_and_reserve_impl(redis, key, Decimal("20"), Decimal("50"))
    outcome = await _budget_core.check_and_reserve_impl(
        redis, key, Decimal("15"), Decimal("50")
    )
    assert outcome.exceeded is False
    assert outcome.new_total == Decimal("35.0")


@pytest.mark.asyncio
async def test_check_and_reserve_exceeded_rolls_back(redis, now_fixed):
    """超限: exceeded=True 且预扣被回滚 (redis 余额回到越界前)."""
    key = _budget_core.daily_key("p", now_fixed)
    # 先到 45
    await redis.set(key, "45.0")
    # 再 reserve 10 → 55 > 50 → 超限回滚
    outcome = await _budget_core.check_and_reserve_impl(
        redis, key, Decimal("10"), Decimal("50")
    )
    assert outcome.exceeded is True
    assert outcome.new_total == Decimal("55.0")  # 越界前总额 (供 wrapper 算 usage)
    # 关键: redis 已回滚到 45 (不是 55)
    assert Decimal(str(await redis.get(key))) == Decimal("45.0")


@pytest.mark.asyncio
async def test_check_and_reserve_exactly_at_limit_not_exceeded(redis, now_fixed):
    """恰好等于 limit 不算超 (> 才超, == 放行)."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "40.0")
    outcome = await _budget_core.check_and_reserve_impl(
        redis, key, Decimal("10"), Decimal("50")
    )
    assert outcome.exceeded is False
    assert outcome.new_total == Decimal("50.0")


@pytest.mark.asyncio
async def test_check_and_reserve_redis_error_raises(now_fixed):
    """redis incrbyfloat 异常 → BudgetCoreRedisError (wrapper 翻译 fail-closed)."""
    key = _budget_core.daily_key("p", now_fixed)
    with pytest.raises(_budget_core.BudgetCoreRedisError):
        await _budget_core.check_and_reserve_impl(
            _BoomRedis(), key, Decimal("10"), Decimal("50")
        )


# ─────────────────────── commit_impl ───────────────────────


@pytest.mark.asyncio
async def test_commit_delta_negative_refunds(redis, now_fixed):
    """actual < reserved → 退款 (redis 减)."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "30.0")
    await _budget_core.commit_impl(redis, key, Decimal("3"), Decimal("5"))
    # delta = 3-5 = -2 → 30-2 = 28
    assert Decimal(str(await redis.get(key))) == Decimal("28.0")


@pytest.mark.asyncio
async def test_commit_delta_positive_charges(redis, now_fixed):
    """actual > reserved → 补扣 (redis 加)."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "30.0")
    await _budget_core.commit_impl(redis, key, Decimal("8"), Decimal("5"))
    # delta = 8-5 = +3 → 33
    assert Decimal(str(await redis.get(key))) == Decimal("33.0")


@pytest.mark.asyncio
async def test_commit_delta_zero_noop(redis, now_fixed):
    """actual == reserved → 不动 redis."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "30.0")
    await _budget_core.commit_impl(redis, key, Decimal("5"), Decimal("5"))
    assert Decimal(str(await redis.get(key))) == Decimal("30.0")


# ─────────────────────── release_impl ───────────────────────


@pytest.mark.asyncio
async def test_release_refunds(redis, now_fixed):
    """退款已预扣额."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "20.0")
    await _budget_core.release_impl(redis, key, Decimal("7"))
    assert Decimal(str(await redis.get(key))) == Decimal("13.0")


@pytest.mark.asyncio
async def test_release_zero_noop(redis, now_fixed):
    """reserved=0 → no-op (不调 redis)."""
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "20.0")
    await _budget_core.release_impl(redis, key, Decimal("0"))
    assert Decimal(str(await redis.get(key))) == Decimal("20.0")


# ─────────────────── get_today_spent_impl ───────────────────


@pytest.mark.asyncio
async def test_get_today_spent_reads(redis, now_fixed):
    key = _budget_core.daily_key("p", now_fixed)
    await redis.set(key, "42.5")
    assert await _budget_core.get_today_spent_impl(redis, key) == Decimal("42.5")


@pytest.mark.asyncio
async def test_get_today_spent_missing_returns_zero(redis, now_fixed):
    key = _budget_core.daily_key("p", now_fixed)
    assert await _budget_core.get_today_spent_impl(redis, key) == Decimal("0")


@pytest.mark.asyncio
async def test_get_today_spent_decodes_bytes(now_fixed):
    """raw bytes → decode → Decimal (真 redis 返 bytes)."""

    class _BytesRedis(_BudgetRedis):
        async def get(self, key):
            return b"17.25"

    key = _budget_core.daily_key("p", now_fixed)
    assert await _budget_core.get_today_spent_impl(_BytesRedis(), key) == Decimal("17.25")


@pytest.mark.asyncio
async def test_get_today_spent_redis_error_returns_zero(now_fixed):
    """get 异常 → 0 (容错, 不抛)."""

    class _BoomGet(_BudgetRedis):
        async def get(self, key):
            raise RuntimeError("redis down")

    key = _budget_core.daily_key("p", now_fixed)
    assert await _budget_core.get_today_spent_impl(_BoomGet(), key) == Decimal("0")
