"""Tests for WebSocket Pub/Sub broker (D-019).

覆盖场景：
1. 单机模式（enabled=False / redis=None）：本地投递可用，publish 被跳过
2. 启用模式：publish 到 Redis；其他实例通过 listen loop 收到后本地 fanout
3. 多实例集成（两个 broker + fakeredis）：A 推送 → B 的 WS 收到
4. Redis 故障降级：start 时订阅失败 → 退化为单机模式，不抛异常
5. 自回显抑制：同 instance_id 的消息不会再次本地投递
6. 连接注册 / 注销
7. 业务侧连接发送失败不影响整体
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.ws.pubsub import (
    DEFAULT_CHANNEL,
    WsPubSubBroker,
    get_current_broker,
    start_ws_pubsub,
    stop_ws_pubsub,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class FakeWebSocket:
    def __init__(self):
        self.sent: list[str] = []
        self.fail = False

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("send fail")
        self.sent.append(text)


class FakePubSub:
    """模拟 redis.asyncio.client.PubSub，支持 subscribe/listen/unsubscribe/close。

    使用 asyncio.Queue 在测试中把"其他实例 publish 的消息"注入进来。
    """

    def __init__(self, bus: "FakeRedisBus", channel_set: set[str]):
        self.bus = bus
        self._channels = channel_set
        self._queue: asyncio.Queue = asyncio.Queue()
        self._closed = False
        bus.listeners.append(self)

    async def subscribe(self, channel: str) -> None:
        self._channels.add(channel)

    async def unsubscribe(self, channel: str) -> None:
        self._channels.discard(channel)

    async def close(self) -> None:
        self._closed = True
        # 唤醒 listen()
        await self._queue.put(None)

    async def deliver(self, channel: str, data: str) -> None:
        if channel in self._channels:
            await self._queue.put({"type": "message", "channel": channel, "data": data})

    async def listen(self):
        while True:
            message = await self._queue.get()
            if message is None:
                return
            yield message


class FakeRedisBus:
    """一个极简的 redis.asyncio.Redis 替身 + pub/sub 总线。"""

    def __init__(self):
        self.listeners: list[FakePubSub] = []
        self._channel_sets: list[set[str]] = []

    def pubsub(self) -> FakePubSub:
        channels: set[str] = set()
        self._channel_sets.append(channels)
        return FakePubSub(self, channels)

    async def publish(self, channel: str, data: str) -> int:
        count = 0
        for ps in list(self.listeners):
            if ps._closed:
                continue
            if channel in ps._channels:
                await ps.deliver(channel, data)
                count += 1
        return count


# ---------------------------------------------------------------------------
# 1. 单机模式：enabled=False
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_disabled_mode_local_delivery_only():
    bus = FakeRedisBus()
    broker = WsPubSubBroker(redis_client=bus, enabled=False)
    await broker.start()

    ws = FakeWebSocket()
    user_id = uuid.uuid4()
    await broker.register(user_id, ws)

    await broker.push_to_user(user_id, {"hello": "world"})
    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0]) == {"hello": "world"}

    # 不应 publish 到 Redis
    assert bus.listeners == []  # 未订阅
    await broker.stop()


# ---------------------------------------------------------------------------
# 2. 单机模式：redis=None
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_no_redis_mode():
    broker = WsPubSubBroker(redis_client=None, enabled=True)
    await broker.start()
    ws = FakeWebSocket()
    user_id = uuid.uuid4()
    await broker.register(user_id, ws)
    await broker.push_to_user(user_id, {"msg": "x"})
    assert len(ws.sent) == 1
    await broker.stop()


# ---------------------------------------------------------------------------
# 3. 启用模式：本地投递 + Redis publish
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_enabled_delivers_locally_and_publishes():
    bus = FakeRedisBus()
    broker = WsPubSubBroker(redis_client=bus, enabled=True)
    await broker.start()

    ws = FakeWebSocket()
    user_id = uuid.uuid4()
    await broker.register(user_id, ws)

    await broker.push_to_user(user_id, {"type": "notification", "k": "v"})

    # 本地投递成功
    assert len(ws.sent) == 1
    payload = json.loads(ws.sent[0])
    assert payload["type"] == "notification"

    await broker.stop()


# ---------------------------------------------------------------------------
# 4. 自回显抑制：同实例 publish 的消息不会被 listen loop 再投递一次
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_suppresses_self_echo():
    bus = FakeRedisBus()
    broker = WsPubSubBroker(redis_client=bus, enabled=True)
    await broker.start()

    ws = FakeWebSocket()
    user_id = uuid.uuid4()
    await broker.register(user_id, ws)

    await broker.push_to_user(user_id, {"k": 1})
    # 给 listen loop 一点时间处理回显
    await asyncio.sleep(0.05)

    # 只应有一次本地投递（来自 push_to_user 的立即 deliver），listen loop 的自回显被跳过
    assert len(ws.sent) == 1
    await broker.stop()


# ---------------------------------------------------------------------------
# 5. 多实例集成：A publish → B 的 WS 收到
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_cross_instance_fanout():
    bus = FakeRedisBus()

    broker_a = WsPubSubBroker(
        redis_client=bus, enabled=True, instance_id="A-xxxx"
    )
    broker_b = WsPubSubBroker(
        redis_client=bus, enabled=True, instance_id="B-yyyy"
    )
    await broker_a.start()
    await broker_b.start()

    # 用户连接在 B 实例上
    user_id = uuid.uuid4()
    ws_on_b = FakeWebSocket()
    await broker_b.register(user_id, ws_on_b)

    # A 实例推送（用户连接不在本机）
    await broker_a.push_to_user(user_id, {"from": "A"})

    # listen loop 异步调度
    for _ in range(20):
        await asyncio.sleep(0.01)
        if ws_on_b.sent:
            break

    assert len(ws_on_b.sent) == 1
    assert json.loads(ws_on_b.sent[0]) == {"from": "A"}

    await broker_a.stop()
    await broker_b.stop()


# ---------------------------------------------------------------------------
# 6. 多实例且用户同时连 A 和 B：A 推送时 A 本地直接送达，B 通过 pubsub 送达
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_multi_instance_user_on_both():
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(redis_client=bus, enabled=True, instance_id="A")
    broker_b = WsPubSubBroker(redis_client=bus, enabled=True, instance_id="B")
    await broker_a.start()
    await broker_b.start()

    user_id = uuid.uuid4()
    ws_a = FakeWebSocket()
    ws_b = FakeWebSocket()
    await broker_a.register(user_id, ws_a)
    await broker_b.register(user_id, ws_b)

    await broker_a.push_to_user(user_id, {"x": 1})

    for _ in range(20):
        await asyncio.sleep(0.01)
        if ws_b.sent:
            break

    assert len(ws_a.sent) == 1  # 本地直送
    assert len(ws_b.sent) == 1  # pubsub fanout
    await broker_a.stop()
    await broker_b.stop()


# ---------------------------------------------------------------------------
# 7. 注册 / 注销 与 count
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_register_unregister():
    broker = WsPubSubBroker(redis_client=None, enabled=False)
    await broker.start()
    user_id = uuid.uuid4()
    ws1 = FakeWebSocket()
    ws2 = FakeWebSocket()
    await broker.register(user_id, ws1)
    await broker.register(user_id, ws2)
    assert broker.local_connection_count(user_id) == 2
    assert broker.local_connection_count() == 2

    await broker.unregister(user_id, ws1)
    assert broker.local_connection_count(user_id) == 1
    await broker.unregister(user_id, ws2)
    assert broker.local_connection_count(user_id) == 0
    await broker.stop()


# ---------------------------------------------------------------------------
# 8. 单连接发送失败不影响其他连接
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_one_failing_ws_does_not_block_others():
    broker = WsPubSubBroker(redis_client=None, enabled=False)
    await broker.start()
    user_id = uuid.uuid4()
    bad = FakeWebSocket()
    bad.fail = True
    good = FakeWebSocket()
    await broker.register(user_id, bad)
    await broker.register(user_id, good)

    await broker.push_to_user(user_id, {"ok": True})

    assert len(good.sent) == 1
    assert len(bad.sent) == 0  # 失败的没写入，但也没抛
    await broker.stop()


# ---------------------------------------------------------------------------
# 9. Redis 订阅失败降级：start 不抛异常，broker 仍可用（单机模式）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_subscribe_failure_fallback_to_local():
    class _BrokenRedis:
        def pubsub(self):
            ps = MagicMock()
            ps.subscribe = AsyncMock(side_effect=RuntimeError("redis down"))
            return ps

        async def publish(self, *a, **kw):
            raise RuntimeError("redis down")

    broker = WsPubSubBroker(redis_client=_BrokenRedis(), enabled=True)
    await broker.start()  # 不抛
    user_id = uuid.uuid4()
    ws = FakeWebSocket()
    await broker.register(user_id, ws)
    # 本地仍可投递
    await broker.push_to_user(user_id, {"k": 1})
    assert len(ws.sent) == 1
    await broker.stop()


# ---------------------------------------------------------------------------
# 10. Publish 失败不影响本地投递（运行中 Redis 故障）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_broker_publish_failure_still_delivers_local():
    class _Bus:
        def __init__(self):
            self._ps = MagicMock()
            self._ps.subscribe = AsyncMock()
            self._ps.unsubscribe = AsyncMock()
            self._ps.close = AsyncMock()

            async def _listen():
                while True:
                    await asyncio.sleep(3600)
                    yield None

            self._ps.listen = _listen

        def pubsub(self):
            return self._ps

        async def publish(self, *a, **kw):
            raise RuntimeError("publish down")

    broker = WsPubSubBroker(redis_client=_Bus(), enabled=True)
    await broker.start()
    user_id = uuid.uuid4()
    ws = FakeWebSocket()
    await broker.register(user_id, ws)
    await broker.push_to_user(user_id, {"k": 2})
    assert len(ws.sent) == 1  # 本地成功
    await broker.stop()


# ---------------------------------------------------------------------------
# 11. lifespan helper：start_ws_pubsub / stop_ws_pubsub / get_current_broker
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_lifespan_helpers_set_and_clear_current_broker():
    class _App:
        def __init__(self):
            self.state = type("S", (), {})()
            self.state.redis = None

    app = _App()
    broker = await start_ws_pubsub(app, enabled=False, channel=DEFAULT_CHANNEL)
    assert get_current_broker() is broker
    assert app.state.ws_broker is broker

    await stop_ws_pubsub(app)
    assert get_current_broker() is None
    assert app.state.ws_broker is None


# ---------------------------------------------------------------------------
# 12. 丢弃异常格式的消息（listen loop 容错）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_listen_loop_ignores_malformed_message():
    bus = FakeRedisBus()
    broker = WsPubSubBroker(redis_client=bus, enabled=True, instance_id="X")
    await broker.start()

    user_id = uuid.uuid4()
    ws = FakeWebSocket()
    await broker.register(user_id, ws)

    # 直接用 bus.publish 灌一个无效 JSON
    await bus.publish(DEFAULT_CHANNEL, "not-json-at-all")
    # 再灌一个缺 user_id 的
    await bus.publish(DEFAULT_CHANNEL, json.dumps({"origin": "other", "payload": {"a": 1}}))
    # 最后灌一个正常的
    await bus.publish(
        DEFAULT_CHANNEL,
        json.dumps({"origin": "other", "user_id": str(user_id), "payload": {"ok": 1}}),
    )

    for _ in range(30):
        await asyncio.sleep(0.01)
        if ws.sent:
            break

    assert len(ws.sent) == 1
    assert json.loads(ws.sent[0]) == {"ok": 1}
    await broker.stop()
