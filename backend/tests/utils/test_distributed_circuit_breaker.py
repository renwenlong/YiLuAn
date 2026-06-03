"""S2-DEV-012 ADR-0040 Phase 1: DistributedCircuitBreaker 单测

5 类场景（acceptance 第 4 项）：
1. 2 worker 同时 OPEN_TIMEOUT_ELAPSED → 只 1 个抢到 probe lock
2. probe lock 持有者探测成功后 (record_success ≥ N) → CLOSED + 释放
3. probe lock 持有者 crash 后 (TTL 过期) → 其他 worker 抢锁重试
4. Redis 不可用 → 降级到本地 CB（不阻断）
5. probe_lock_ttl per provider 配置生效
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.utils.distributed_circuit_breaker import (
    DEFAULT_PROBE_LOCK_TTL,
    DistributedCircuitBreaker,
    default_probe_lock_ttl,
    set_distributed_redis_client,
)


# ---------------------------------------------------------------------------
# Fake Redis：模拟 SETNX 行为 + TTL
# ---------------------------------------------------------------------------


class FakeRedis:
    """最小实现：SET nx=True ex=N → 抢锁；含 TTL 过期。"""

    def __init__(self) -> None:
        self.store: dict[str, tuple[str, float]] = {}  # key -> (value, expires_at)
        self.set_calls: list[tuple] = []

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> bool | None:
        self.set_calls.append((key, value, nx, ex))
        now = time.monotonic()
        # 过期清理
        if key in self.store and self.store[key][1] <= now:
            del self.store[key]
        if nx and key in self.store:
            return None  # 抢锁失败
        expires = now + (ex if ex else 86400)
        self.store[key] = (value, expires)
        return True

    def fast_forward_ttl(self, seconds: float) -> None:
        """模拟时间流逝：将所有 entry 的 expires_at 提前 seconds 秒。"""
        for k in list(self.store):
            v, exp = self.store[k]
            self.store[k] = (v, exp - seconds)


@pytest.fixture(autouse=True)
def reset_redis_client():
    """每 case 清掉 _redis_client 全局，避免污染。"""
    set_distributed_redis_client(None)
    yield
    set_distributed_redis_client(None)


# ---------------------------------------------------------------------------
# 场景 1：2 worker 同时进 OPEN_TIMEOUT_ELAPSED 只 1 个抢到锁
# ---------------------------------------------------------------------------


def test_two_workers_only_one_acquires_probe_lock():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    # 模拟 2 worker 各持一个本地 CB 实例（不同进程 → 不同 dict）
    cb_w1 = DistributedCircuitBreaker(threshold=3, timeout=10, provider="wxpay")
    cb_w2 = DistributedCircuitBreaker(threshold=3, timeout=10, provider="wxpay")

    # 让两个都处于 OPEN 且 timeout 已到
    cb_w1.state = cb_w1.OPEN
    cb_w1._opened_at = time.monotonic() - 11
    cb_w2.state = cb_w2.OPEN
    cb_w2._opened_at = time.monotonic() - 11

    # worker 1 先 allow_request → 抢到锁，转 HALF_OPEN
    assert cb_w1.allow_request() is True
    assert cb_w1.state == cb_w1.HALF_OPEN

    # worker 2 后 allow_request → 锁被 w1 占着，拒，保持 OPEN
    assert cb_w2.allow_request() is False
    assert cb_w2.state == cb_w2.OPEN

    # 只 1 次 SETNX 写真锁（其他都是 set_calls 记录，但 nx 第二次返回 None）
    assert len(fake.set_calls) == 2  # 两次调用 SET
    assert fake.set_calls[0][0] == "cb:wxpay:probe_lock"
    assert fake.set_calls[1][0] == "cb:wxpay:probe_lock"


# ---------------------------------------------------------------------------
# 场景 2：probe lock 持有者探测成功后 CLOSED
# ---------------------------------------------------------------------------


def test_probe_holder_recovers_to_closed():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb = DistributedCircuitBreaker(
        threshold=3, timeout=10, provider="mock", half_open_success_threshold=2
    )
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 11

    assert cb.allow_request() is True  # 抢锁 → HALF_OPEN
    assert cb.state == cb.HALF_OPEN

    # 探测 2 次成功 → CLOSED
    cb.record_success()
    assert cb.state == cb.HALF_OPEN  # 还没到 threshold=2
    cb.record_success()
    assert cb.state == cb.CLOSED


# ---------------------------------------------------------------------------
# 场景 3：probe lock 持有者 crash 后其他 worker 抢锁
# ---------------------------------------------------------------------------


def test_other_worker_acquires_after_probe_lock_ttl_expires():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb_w1 = DistributedCircuitBreaker(
        threshold=3, timeout=10, provider="mock"
    )  # TTL=2s
    cb_w2 = DistributedCircuitBreaker(threshold=3, timeout=10, provider="mock")

    cb_w1.state = cb_w1.OPEN
    cb_w1._opened_at = time.monotonic() - 11
    cb_w2.state = cb_w2.OPEN
    cb_w2._opened_at = time.monotonic() - 11

    assert cb_w1.allow_request() is True  # w1 抢到
    assert cb_w2.allow_request() is False  # w2 被拒

    # 模拟 w1 crash + TTL 过期
    fake.fast_forward_ttl(5)

    # w2 重试 → 抢到锁
    assert cb_w2.allow_request() is True
    assert cb_w2.state == cb_w2.HALF_OPEN


# ---------------------------------------------------------------------------
# 场景 4：Redis 不可用降级到本地 CB
# ---------------------------------------------------------------------------


def test_redis_unavailable_falls_back_to_local_cb():
    # 不设 redis client → 降级
    set_distributed_redis_client(None)

    cb = DistributedCircuitBreaker(threshold=3, timeout=10, provider="wxpay")
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 11

    # 没 Redis → SETNX 降级返回 True → 仍允许探测（不阻断业务）
    assert cb.allow_request() is True
    assert cb.state == cb.HALF_OPEN


def test_redis_exception_falls_back_to_local_cb():
    """Redis client 存在但调用抛异常 → 降级"""
    failing = MagicMock()
    failing.set.side_effect = RuntimeError("connection refused")
    set_distributed_redis_client(failing)

    cb = DistributedCircuitBreaker(threshold=3, timeout=10, provider="wxpay")
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 11

    assert cb.allow_request() is True  # 降级允许
    assert cb.state == cb.HALF_OPEN


# ---------------------------------------------------------------------------
# 场景 5：probe_lock_ttl per provider 配置
# ---------------------------------------------------------------------------


def test_default_probe_lock_ttl_per_provider():
    assert default_probe_lock_ttl("wxpay") == 8.0
    assert default_probe_lock_ttl("wechat_pay") == 8.0  # providers/payment/wechat.py 名
    assert default_probe_lock_ttl("deepseek") == 5.0
    assert default_probe_lock_ttl("aliyun_sms") == 3.0
    assert default_probe_lock_ttl("mock") == 2.0
    # 未知 provider → fallback 5s
    assert default_probe_lock_ttl("unknown_provider") == 5.0


def test_probe_lock_ttl_passed_to_redis_setnx():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb = DistributedCircuitBreaker(threshold=3, timeout=10, provider="wxpay")
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 11

    cb.allow_request()
    # 验证 SETNX 调用的 ex 参数 = 8（wxpay 默认 TTL）
    assert fake.set_calls[0][3] == 8  # ex


def test_probe_lock_ttl_explicit_override():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb = DistributedCircuitBreaker(
        threshold=3, timeout=10, provider="custom", probe_lock_ttl=15.0
    )
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 11

    cb.allow_request()
    assert fake.set_calls[0][3] == 15


# ---------------------------------------------------------------------------
# CLOSED / OPEN 时间未到 - 不抢锁
# ---------------------------------------------------------------------------


def test_closed_state_does_not_touch_redis():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb = DistributedCircuitBreaker(threshold=3, timeout=10, provider="mock")
    # 默认 CLOSED
    assert cb.allow_request() is True
    assert len(fake.set_calls) == 0  # 没有 SETNX 调用


def test_open_within_timeout_does_not_touch_redis():
    fake = FakeRedis()
    set_distributed_redis_client(fake)

    cb = DistributedCircuitBreaker(threshold=3, timeout=10, provider="mock")
    cb.state = cb.OPEN
    cb._opened_at = time.monotonic() - 5  # timeout 还没到

    assert cb.allow_request() is False
    assert len(fake.set_calls) == 0  # 没有 SETNX 调用


def test_default_probe_lock_ttl_table_contains_all_known_providers():
    """DEFAULT_PROBE_LOCK_TTL 表必须含所有 outbound 接入的 provider。"""
    assert "wxpay" in DEFAULT_PROBE_LOCK_TTL
    assert "wechat_pay" in DEFAULT_PROBE_LOCK_TTL
    assert "deepseek" in DEFAULT_PROBE_LOCK_TTL
    assert "aliyun_sms" in DEFAULT_PROBE_LOCK_TTL
    assert "mock" in DEFAULT_PROBE_LOCK_TTL
