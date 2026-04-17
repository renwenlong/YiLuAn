"""Tests for WsPubSubBroker.register_with_cap (D-020).

覆盖：
- 在限制范围内正常注册，不触发踢人
- 超过 max_connections 时踢最早连接
- max_connections <= 0 视为不限制
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from app.ws.pubsub import WsPubSubBroker


class FakeWebSocket:
    def __init__(self, name: str = ""):
        self.name = name
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, text: str) -> None:
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_register_with_cap_within_limit_no_eviction():
    broker = WsPubSubBroker(redis_client=None, enabled=False, key_field="user_id")
    broker._started = True  # 跳过 lifespan

    user_id = uuid4()
    ws1 = FakeWebSocket("ws1")
    ws2 = FakeWebSocket("ws2")
    ws3 = FakeWebSocket("ws3")

    evicted1 = await broker.register_with_cap(user_id, ws1, max_connections=3)
    evicted2 = await broker.register_with_cap(user_id, ws2, max_connections=3)
    evicted3 = await broker.register_with_cap(user_id, ws3, max_connections=3)

    assert evicted1 == []
    assert evicted2 == []
    assert evicted3 == []
    assert broker.local_connection_count(user_id) == 3
    assert not ws1.closed and not ws2.closed and not ws3.closed


@pytest.mark.asyncio
async def test_register_with_cap_evicts_oldest_when_exceed():
    broker = WsPubSubBroker(redis_client=None, enabled=False, key_field="user_id")
    broker._started = True

    user_id = uuid4()
    ws1 = FakeWebSocket("ws1")
    ws2 = FakeWebSocket("ws2")
    ws3 = FakeWebSocket("ws3")
    ws4 = FakeWebSocket("ws4")

    await broker.register_with_cap(user_id, ws1, max_connections=3)
    await broker.register_with_cap(user_id, ws2, max_connections=3)
    await broker.register_with_cap(user_id, ws3, max_connections=3)
    evicted = await broker.register_with_cap(user_id, ws4, max_connections=3)

    # 第 4 条接入时，最老的 ws1 被返回作为 to_evict
    assert evicted == [ws1]
    # 本地表里只剩 ws2/ws3/ws4
    assert broker.local_connection_count(user_id) == 3
    # 调用方负责 close；broker 仅返回引用，这里手动验证行为
    for ws in evicted:
        await ws.close(code=4008, reason="Replaced")
    assert ws1.closed is True
    assert ws2.closed is False


@pytest.mark.asyncio
async def test_register_with_cap_zero_means_unlimited():
    broker = WsPubSubBroker(redis_client=None, enabled=False, key_field="user_id")
    broker._started = True

    user_id = uuid4()
    for i in range(10):
        evicted = await broker.register_with_cap(
            user_id, FakeWebSocket(f"ws{i}"), max_connections=0
        )
        assert evicted == []
    assert broker.local_connection_count(user_id) == 10


@pytest.mark.asyncio
async def test_register_with_cap_bulk_overflow_evicts_multiple():
    """若外部调用者在短时间内跨 await 点注册多条，单次调用最多踢到降到阈值。"""
    broker = WsPubSubBroker(redis_client=None, enabled=False, key_field="user_id")
    broker._started = True

    user_id = uuid4()
    # 先塞 5 条（cap=0 不限制）
    wss = [FakeWebSocket(f"ws{i}") for i in range(5)]
    for ws in wss:
        await broker.register_with_cap(user_id, ws, max_connections=0)
    assert broker.local_connection_count(user_id) == 5

    # 现在用 cap=3 再加一条 → 应踢掉前 3 条（5+1=6，需降到 3，故 overflow=3）
    ws_new = FakeWebSocket("new")
    evicted = await broker.register_with_cap(user_id, ws_new, max_connections=3)
    assert [w.name for w in evicted] == ["ws0", "ws1", "ws2"]
    assert broker.local_connection_count(user_id) == 3
