"""
Cross-replica precheck broadcast — in-process mock harness E2E
(S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E AC#2).

设计动机
========

ADR-0048 §4.1 + ADR-0053 §AC#5 描述了 quantitative 跨副本测试的两条路径:

1. **真 docker 双副本路径** (test_ai_blocklist_pubsub_cross_replica.py 模式)
   - `@pytest.mark.docker` opt-in, staging stack up 后手动跑
   - 验证: nginx upstream round-robin + 真 Redis pub/sub + WS connection 跨容器

2. **in-process 双 broker 路径** (本文件)
   - 默认 CI 跑 (无外部依赖, < 2s)
   - 复用 ``backend/tests/test_ws_pubsub.py`` 的 ``FakeRedisBus`` + 双 broker
     模式 (line 197-228 ``test_broker_cross_instance_fanout``)
   - 验证: 同一 ``FakeRedisBus`` 上两个 broker 实例 (副本 A / 副本 B), 副本 A
     调 ``broadcast_status_updated`` → 副本 B 上注册的 ws 收到 3 个事件 (3 broadcast
     函数各一个)

为何两条路径并存
================

| 维度 | docker 路径 | mock harness 路径 |
|------|-------------|-------------------|
| CI 跑 | ❌ staging only | ✅ 默认每次跑 |
| 真 Redis | ✅ | ❌ FakeRedisBus |
| 真 WS connection | ✅ httpx-ws | ❌ FakeWebSocket |
| 跨进程隔离 | ✅ docker container | ❌ in-process |
| 验证目标 | 真 prod 流量行为 | broker contract / pubsub envelope 协议 |
| 跑时 | 数十秒 (docker up + warm) | < 2s |

mock harness 的价值: **锁住 broker 协议契约不漏**, 防止以下 regression:
- ``broadcast_status_updated`` 改 envelope schema 漏 ``card`` 字段 →
  ``test_replica_b_receives_status_updated_from_replica_a`` 会爆
- ``broadcast_all_ready`` 漏 publish (本地直送但跨副本丢) →
  ``test_replica_b_receives_all_ready_from_replica_a`` 会爆
- ``broadcast_blocked`` reason 字段 drift → 对应 test 会爆
- 三个 broadcast 函数都换 key_field 但只改了 user 一处, 漏改 order_id 路径 →
  整个文件都会爆 (broker key_field="order_id" 不 match)
- self-echo 抑制 (instance_id check) 退化 →
  ``test_replica_a_does_not_double_deliver_self_echo`` 会爆

docker 路径关 staging quantitative window 跑, mock harness 路径关每次 CI gate
跑, 互补不互替。

测试范围 (本文件)
=================

| AC# (S3-TEST-003-PRECHECK-CROSS-REPLICA-E2E) | 覆盖 |
|-----------------------------------------------|-----|
| AC#1 staging k6 SLO | ❌ 不在本文件 (k6 staging window) |
| AC#2 跨副本 broadcast 时序 + 幂等 | ✅ 本文件 5 test |
| AC#3 default pytest deselect docker marker | ✅ 本文件无 ``@docker`` marker, 默认跑 |
| AC#4 测试报告落 tests/test-report... | ❌ 文档 task |

依赖
====

- ``WsPubSubBroker`` (backend/app/ws/pubsub.py, key_field="order_id")
- ``broadcast_status_updated`` / ``broadcast_all_ready`` / ``broadcast_blocked``
  (backend/app/services/precheck_broadcast.py)
- ``FakeRedisBus`` / ``FakePubSub`` / ``FakeWebSocket`` (引自
  backend/tests/test_ws_pubsub.py, 重复定义避免 cross-file fixture coupling)

为何 mock harness 重复定义而非 import
======================================

``test_ws_pubsub.py`` 是 user-broker 维度的 unit test, 本文件是 precheck-broker
维度的 contract test。共享 ``FakeRedisBus`` import 会让 unit test refactor 影响
contract test, 反之亦然。重复 ~80 行 FakeRedisBus 是 ADR-0048 §3.5 提倡的
"测试代码低耦合优于代码 DRY" 原则。

跑法
====

默认 CI / 本地::

    backend/.venv/bin/python -m pytest \
        backend/tests/e2e/test_e2e_precheck_pubsub_cross_replica.py -v

跨副本同套件 (含 docker marker 真双副本, staging only)::

    backend/.venv/bin/python -m pytest \
        backend/tests/e2e/ -v -m "not docker"
"""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.services.precheck_broadcast import (
    PRECHECK_PUBSUB_CHANNEL,
    broadcast_all_ready,
    broadcast_blocked,
    broadcast_status_updated,
)
from app.ws.pubsub import WsPubSubBroker

pytestmark = [pytest.mark.asyncio, pytest.mark.e2e]


# ---------------------------------------------------------------------------
# Fake harness (在 backend/tests/test_ws_pubsub.py 已有同名 class, 本文件
# 重复定义保持 contract test 解耦, 见 module docstring "为何 mock harness
# 重复定义而非 import")
# ---------------------------------------------------------------------------
class FakeWebSocket:
    """模拟 WebSocket, 把 push 的 payload 收集到 ``sent`` 列表。"""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.fail: bool = False
        self.closed_with: tuple[int, str] | None = None

    async def send_text(self, text: str) -> None:
        if self.fail:
            raise RuntimeError("send fail (FakeWebSocket.fail=True)")
        self.sent.append(text)

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.closed_with = (code, reason)


class FakePubSub:
    """模拟 redis.asyncio.client.PubSub, 用 asyncio.Queue 把其他 broker
    publish 的消息注入。
    """

    def __init__(self, bus: "FakeRedisBus", channel_set: set[str]) -> None:
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
    """极简 redis.asyncio.Redis 替身 + pub/sub 总线 (跨 broker 共享)。

    跨副本测试关键: 两个 broker 共用一个 bus, broker_a 上 publish 的消息
    通过 bus.listeners 转给 broker_b 的 FakePubSub 队列。
    """

    def __init__(self) -> None:
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
# Helpers
# ---------------------------------------------------------------------------
async def _wait_for_ws_message(
    ws: FakeWebSocket,
    *,
    expected_count: int = 1,
    sla_ms: int = 1000,
) -> None:
    """等 ``ws.sent`` 达到 ``expected_count``, 上限 ``sla_ms`` (ms)。

    跨副本 broadcast 通过 listen loop 异步调度, 必须 ``await asyncio.sleep``
    给 event loop 一个轮转机会; 不能用 ``time.sleep``。
    """
    steps = max(1, sla_ms // 10)
    for _ in range(steps):
        await asyncio.sleep(0.01)
        if len(ws.sent) >= expected_count:
            return
    raise AssertionError(
        f"ws.sent expected >={expected_count} within {sla_ms}ms, got "
        f"{len(ws.sent)} (sent={ws.sent!r})"
    )


def _build_fake_app(broker: WsPubSubBroker) -> MagicMock:
    """构造一个最小 fake FastAPI app, 让 ``get_or_create_precheck_broker``
    能从 ``app.state.ws_precheck_broker`` 取到我们传的 broker。

    ``precheck_broadcast`` 三个 broadcast 函数全靠这个 lookup 路径找 broker,
    不能用真 FastAPI app (会触发整个 lifespan 跑起来)。
    """
    app = MagicMock()
    app.state.ws_precheck_broker = broker
    return app


# ---------------------------------------------------------------------------
# Test 1 — status.updated 跨副本 (副本 A push → 副本 B 上 ws 收到)
# ---------------------------------------------------------------------------
async def test_replica_b_receives_status_updated_from_replica_a():
    """AC#2 副本 A 调 broadcast_status_updated → 副本 B 上注册的 ws 收到。"""
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_b = FakeWebSocket()
        await broker_b.register(order_id, ws_on_b)

        # 副本 A 调 (用户连接不在副本 A)
        app_a = _build_fake_app(broker_a)
        await broadcast_status_updated(
            app_a,
            order_id,
            card="contract",
            status={"contract_status": "ready", "contract_signed_at": "2026-06-11T08:00:00Z"},
            all_ready=False,
        )

        # 副本 B 上的 ws 应通过 pubsub 收到
        await _wait_for_ws_message(ws_on_b, expected_count=1, sla_ms=1000)

        envelope = json.loads(ws_on_b.sent[0])
        assert envelope["event"] == "precheck.status.updated"
        assert envelope["order_id"] == str(order_id)
        assert envelope["card"] == "contract"
        assert envelope["status"] == {
            "contract_status": "ready",
            "contract_signed_at": "2026-06-11T08:00:00Z",
        }
        assert envelope["all_ready"] is False
        assert "ts" in envelope
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 2 — all_ready 跨副本
# ---------------------------------------------------------------------------
async def test_replica_b_receives_all_ready_from_replica_a():
    """AC#2 副本 A 调 broadcast_all_ready → 副本 B 上 ws 收到。"""
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_b = FakeWebSocket()
        await broker_b.register(order_id, ws_on_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_all_ready(app_a, order_id)

        await _wait_for_ws_message(ws_on_b, expected_count=1, sla_ms=1000)

        envelope = json.loads(ws_on_b.sent[0])
        assert envelope["event"] == "precheck.all_ready"
        assert envelope["order_id"] == str(order_id)
        assert "ts" in envelope
        # all_ready 不带 reason / card / status (envelope shape lock)
        assert "reason" not in envelope
        assert "card" not in envelope
        assert "status" not in envelope
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 3 — blocked 跨副本
# ---------------------------------------------------------------------------
async def test_replica_b_receives_blocked_from_replica_a():
    """AC#2 副本 A 调 broadcast_blocked → 副本 B 上 ws 收到, reason 字段不漏。"""
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_b = FakeWebSocket()
        await broker_b.register(order_id, ws_on_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_blocked(
            app_a,
            order_id,
            reason="contract_status=blocked: 文件未在 7 天内上传",
        )

        await _wait_for_ws_message(ws_on_b, expected_count=1, sla_ms=1000)

        envelope = json.loads(ws_on_b.sent[0])
        assert envelope["event"] == "precheck.blocked"
        assert envelope["order_id"] == str(order_id)
        assert envelope["reason"] == "contract_status=blocked: 文件未在 7 天内上传"
        assert "ts" in envelope
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 4 — 副本 A 不向自己 double deliver (self-echo 抑制)
# ---------------------------------------------------------------------------
async def test_replica_a_does_not_double_deliver_self_echo():
    """副本 A 本地直送 + Redis publish, listen loop 收到自己 publish 的消息
    时必须按 ``origin == instance_id`` 跳过, 不能给自己 ws double deliver。

    regression防范: 如果 ``WsPubSubBroker._listen_loop`` self-echo check 退化,
    副本 A 上的 ws 会收到 2 条相同消息 (本地直送 + pubsub 回灌)。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_a = FakeWebSocket()
        await broker_a.register(order_id, ws_on_a)

        app_a = _build_fake_app(broker_a)
        await broadcast_all_ready(app_a, order_id)

        # 给 event loop 充分时间让 listen loop 跑过自己 publish 的消息
        await asyncio.sleep(0.15)

        # ws_on_a 只该收 1 条 (本地直送), 不该收 2 条
        assert len(ws_on_a.sent) == 1, (
            f"self-echo 抑制失效: 副本 A 给自己 ws double deliver, "
            f"sent={ws_on_a.sent!r}"
        )
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 5 — 同 order_id 同时连两副本: A 推 → A 本地直送 + B 通过 pubsub 收到
# ---------------------------------------------------------------------------
async def test_same_order_on_both_replicas_receives_via_both_paths():
    """AC#2 用户同 order_id 同时连 A 和 B (两端 ws), A push 时:

    - ws_a: A 本地直送, 1 条
    - ws_b: A publish → bus → B subscribe → 投递, 1 条

    防范 regression: ``push_to_key`` 本地直送 + Redis publish 双通道任一退化,
    这条 test 会爆。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_a = FakeWebSocket()
        ws_b = FakeWebSocket()
        await broker_a.register(order_id, ws_a)
        await broker_b.register(order_id, ws_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_status_updated(
            app_a,
            order_id,
            card="preparation",
            status={"preparation_status": "ready", "preparation_id": "prep-001"},
            all_ready=False,
        )

        # A 本地直送应已 sync 完成
        assert len(ws_a.sent) == 1, "A 本地直送失败"
        envelope_a = json.loads(ws_a.sent[0])
        assert envelope_a["card"] == "preparation"

        # B 跨副本 listen loop 异步, 等到位
        await _wait_for_ws_message(ws_b, expected_count=1, sla_ms=1000)

        envelope_b = json.loads(ws_b.sent[0])
        assert envelope_b["card"] == "preparation"
        # A 与 B 收到的 envelope 内容一致 (除 ts 可能 ±1s, 这里是同步 push 所以 ts 应一样)
        assert envelope_a["order_id"] == envelope_b["order_id"]
        assert envelope_a["status"] == envelope_b["status"]
        assert envelope_a["event"] == envelope_b["event"]
        assert envelope_a["all_ready"] == envelope_b["all_ready"]
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 6 — 不同 order_id 隔离: A push order_1 不应送到 B 上注册 order_2 的 ws
# ---------------------------------------------------------------------------
async def test_cross_order_isolation_no_leak_between_orders():
    """AC#2 副本 A push order_1, 副本 B 上注册 order_2 的 ws 不该收到任何消息。

    防范 regression: ``push_to_key`` 用 ``order_id`` 维度路由, 如果 channel 维度
    路由退化成"任何 publish 都 fanout 给所有 ws", 这条 test 会爆。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_1 = uuid.uuid4()
        order_2 = uuid.uuid4()
        ws_for_order_2_on_b = FakeWebSocket()
        await broker_b.register(order_2, ws_for_order_2_on_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_status_updated(
            app_a,
            order_1,
            card="insurance",
            status={"insurance_status": "ready"},
            all_ready=False,
        )

        # 给 event loop 充分时间让 pubsub 跑过, 然后断言 order_2 ws 没收到
        await asyncio.sleep(0.15)

        assert len(ws_for_order_2_on_b.sent) == 0, (
            f"cross-order leak: order_1 push 错送到 order_2 ws, "
            f"sent={ws_for_order_2_on_b.sent!r}"
        )
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 7 — 3 broadcast 事件按顺序到达 (status.updated → all_ready → blocked)
# ---------------------------------------------------------------------------
async def test_three_broadcasts_arrive_in_order_on_replica_b():
    """AC#2 副本 A 按 status.updated → all_ready → blocked 顺序 push,
    副本 B 上的 ws 应按相同顺序收到 3 条 (Redis pub/sub 保序契约)。

    防范 regression: 如果 listen loop 用并发 task fanout 没用 queue 顺序,
    跨副本到达顺序可能乱, 这条 test 会爆。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_b = FakeWebSocket()
        await broker_b.register(order_id, ws_on_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_status_updated(
            app_a,
            order_id,
            card="contract",
            status={"contract_status": "ready"},
            all_ready=False,
        )
        await broadcast_all_ready(app_a, order_id)
        await broadcast_blocked(app_a, order_id, reason="late blocked event")

        await _wait_for_ws_message(ws_on_b, expected_count=3, sla_ms=2000)

        events = [json.loads(s)["event"] for s in ws_on_b.sent]
        assert events == [
            "precheck.status.updated",
            "precheck.all_ready",
            "precheck.blocked",
        ], (
            f"跨副本事件顺序错乱: 期望 [status.updated, all_ready, blocked], "
            f"实际 {events}"
        )
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 8 — broker disabled (单副本模式) 不 publish 到 Redis
# ---------------------------------------------------------------------------
async def test_disabled_broker_does_not_leak_to_other_replicas():
    """AC#2 broker_a 设 enabled=False (回退单副本模式), 副本 B 不该收到任何消息。

    这是降级路径契约: 如果 Redis 不可用或配置关 ``WS_PUBSUB_ENABLED``,
    单副本本地直送应正常, 跨副本静默 (不报错也不投递)。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=False,  # ← 降级
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_a = FakeWebSocket()
        ws_on_b = FakeWebSocket()
        await broker_a.register(order_id, ws_on_a)
        await broker_b.register(order_id, ws_on_b)

        app_a = _build_fake_app(broker_a)
        await broadcast_status_updated(
            app_a,
            order_id,
            card="contract",
            status={"contract_status": "ready"},
            all_ready=False,
        )

        # A 本地直送应正常
        assert len(ws_on_a.sent) == 1
        # B 不该收到 (disabled 不 publish)
        await asyncio.sleep(0.15)
        assert len(ws_on_b.sent) == 0, (
            f"disabled broker 错误地 publish 到了 Redis, ws_on_b.sent={ws_on_b.sent!r}"
        )
    finally:
        await broker_a.stop()
        await broker_b.stop()


# ---------------------------------------------------------------------------
# Test 9 — 副本 B push order_1, 副本 A 上注册 order_1 的 ws 也收到 (反方向)
# ---------------------------------------------------------------------------
async def test_replica_a_receives_status_updated_from_replica_b():
    """AC#2 对称性: 副本 B push → 副本 A 上 ws 收到 (验证 pubsub 不是单向)。

    test 1-3 都是 A → B, 这条反方向 B → A, 防范 listen loop 只在一个方向工作。
    """
    bus = FakeRedisBus()
    broker_a = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-A",
    )
    broker_b = WsPubSubBroker(
        redis_client=bus,
        enabled=True,
        channel=PRECHECK_PUBSUB_CHANNEL,
        key_field="order_id",
        instance_id="replica-B",
    )
    await broker_a.start()
    await broker_b.start()
    try:
        order_id = uuid.uuid4()
        ws_on_a = FakeWebSocket()
        await broker_a.register(order_id, ws_on_a)

        app_b = _build_fake_app(broker_b)
        await broadcast_status_updated(
            app_b,
            order_id,
            card="companion_cert",
            status={"companion_cert_status": "ready"},
            all_ready=True,
        )

        await _wait_for_ws_message(ws_on_a, expected_count=1, sla_ms=1000)
        envelope = json.loads(ws_on_a.sent[0])
        assert envelope["card"] == "companion_cert"
        assert envelope["all_ready"] is True
    finally:
        await broker_a.stop()
        await broker_b.stop()
