"""Tests for A21-03: ws Redis pub/sub egress wrapped with outbound decorator.

Coverage:
1. Redis ``publish`` 超时时装饰器正确触发重试，最终 swallow 不抛、本地仍投递。
2. 熔断打开后 ``push_to_key`` 仍 swallow（不向上抛）、本地仍投递。
"""
from __future__ import annotations

import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils.outbound import reset_circuit_breakers
from app.ws.pubsub import WsPubSubBroker


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


@pytest.fixture(autouse=True)
def _reset_breakers():
    """每个用例独立的熔断器状态。"""
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


def _make_broker(publish_side_effect) -> WsPubSubBroker:
    """构造一个最小可用 broker：redis.publish 受控，pubsub 标记为已启动。"""
    fake_redis = MagicMock()
    fake_redis.publish = AsyncMock(side_effect=publish_side_effect)

    broker = WsPubSubBroker(
        redis_client=fake_redis,
        channel="test:a21-03",
        enabled=True,
        instance_id="inst-test",
        key_field="user_id",
    )
    # 跳过真实 start()（不需要订阅/listen loop），但要让 push_to_key
    # 进入 publish 分支：需要 _pubsub 非 None。
    broker._pubsub = MagicMock()
    broker._started = True
    return broker


@pytest.mark.asyncio
async def test_publish_timeout_triggers_retry_then_swallows(caplog):
    """A21-03: redis.publish 一直超时 → 装饰器重试到耗尽 → push_to_key swallow。

    断言：
      * publish 被调用 max_retries+1 = 3 次
      * push_to_key 不向上抛任何异常
      * 本地连接仍然收到了消息
      * 错误日志为 ERROR 级且包含结构化字段
    """
    async def _slow_publish(channel, payload):
        # 远超 outbound timeout=2.0s，但用 sleep + asyncio.wait_for 应在 2s 内中断
        await asyncio.sleep(10)

    broker = _make_broker(publish_side_effect=_slow_publish)
    ws = _FakeWs()
    await broker.register("user-42", ws)  # type: ignore[arg-type]

    caplog.set_level(logging.ERROR, logger="app.ws.pubsub")

    # 不应抛
    await broker.push_to_key("user-42", {"hello": "world"})

    # 1. 本地投递成功（先于 publish）
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0]) == {"hello": "world"}

    # 2. publish 被调用 3 次（max_retries=2，外加首次 = 3）
    assert broker.redis.publish.await_count == 3

    # 3. swallow 后留下 ERROR 日志，含结构化字段
    err_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(err_records) == 1
    msg = err_records[0].getMessage()
    assert "ws_pubsub publish failed" in msg
    assert "channel=test:a21-03" in msg
    assert "key=user-42" in msg
    assert "instance=inst-test" in msg
    assert "error_type=" in msg


@pytest.mark.asyncio
async def test_circuit_breaker_open_still_swallowed(caplog):
    """A21-03: 装饰器 5 次失败后熔断打开，下一次 push_to_key 仍 swallow 不抛。

    断言：
      * 触发足够多失败让熔断打开
      * 熔断打开后再调用一次：本地仍投递、不抛、记录 ERROR 日志
      * 熔断打开后 redis.publish 不再被实际调用（短路）
    """
    async def _always_fail(channel, payload):
        # 装饰器只对 ``RetryableError`` 与 ``asyncio.TimeoutError`` 计入熔断；
        # 其他异常会直通而不调用 record_failure（详见 outbound.py）。
        # 用 RetryableError 模拟 redis 的可重试故障（连接重置 / 超时类）。
        from app.utils.outbound import RetryableError
        raise RetryableError("redis publish failed")

    broker = _make_broker(publish_side_effect=_always_fail)
    ws = _FakeWs()
    await broker.register("user-99", ws)  # type: ignore[arg-type]

    caplog.set_level(logging.ERROR, logger="app.ws.pubsub")

    # 触发熔断：默认 threshold=5。每次 push_to_key 走装饰器内重试
    # max_retries+1=3 次 → record_failure 3 次。两次 push_to_key 累计
    # 6 次 record_failure，已超过 threshold=5，熔断会在第二次结束时打开。
    for _ in range(2):
        await broker.push_to_key("user-99", {"n": 1})

    publish_calls_before = broker.redis.publish.await_count
    # 预期：第一次 push 完整重试 3 次 → failure_count=3。
    # 第二次 push 的第二次重试让 failure_count 到达 threshold=5,
    # 熔断打开；第二次 push 的第三次重试被 cb.allow_request() 短路，
    # 不再调用 redis.publish 。总调用数 = 3 + 2 = 5。
    assert publish_calls_before == 5, (
        f"expected 5 publish calls (circuit opens mid 2nd push), got {publish_calls_before}"
    )

    # 第三次：熔断应已 OPEN，装饰器内部 cb.allow_request() 返回 False，
    # 不会再真正调用 redis.publish；外层仍 swallow。
    caplog.clear()
    ws.sent.clear()
    await broker.push_to_key("user-99", {"n": 2})

    # 1. 本地仍投递
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0]) == {"n": 2}

    # 2. publish 没有再被真实调用（被熔断短路）
    assert broker.redis.publish.await_count == publish_calls_before

    # 3. ERROR 日志仍打出（来自外层 swallow），含 error_type=RetryableError
    err_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(err_records) >= 1
    last = err_records[-1].getMessage()
    assert "ws_pubsub publish failed" in last
    assert "RetryableError" in last  # 熔断短路抛 RetryableError("Circuit breaker open ...")
