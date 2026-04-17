"""WebSocket Redis Pub/Sub 广播器（D-019 多副本支持）。

## 背景
D-017 的 `_notification_connections` 是进程内 dict，在 K8s / ACA 多副本场景下，
一条通知只能送达“用户连接所在”的那个副本；用户连接的实例和触发通知的实例不同
时，推送就会丢失。本模块通过 Redis Pub/Sub 解决此问题。

## 架构
1. 每个副本启动时订阅统一频道 `channel`
2. 本副本维护 `_local: dict[key, list[WebSocket]]`；key 的含义由 broker 使用方决定
   （通知广播器用 `user_id`，聊天广播器用 `order_id`）
3. 推送时：
   - **立即本地投递** + **publish 到 Redis 频道**（双通道，低延迟 + 跨副本）
4. 消息体带 `origin` 标识当前实例 ID；pubsub 监听协程收到消息时：
   - 若 `origin == self.instance_id` → 跳过（本机已投递，避免双发）
   - 否则 → 查本地表投递（其他副本产生的消息）

## 聊天 vs 通知
- 通知广播器：`key = user_id`（跨订单/全局推送给某个用户的多端连接）
- 聊天广播器：`key = order_id`（同订单参与者进同一房间）
- 两者复用同一份 broker 类，仅 channel 和 key 语义不同

## 降级策略
- Redis 不可用或订阅失败 → 记录告警日志，退化为单机内存广播（best-effort）；
  业务不阻塞
- 配置开关 `WS_PUBSUB_ENABLED` / `WS_CHAT_PUBSUB_ENABLED` → 完全关闭 Pub/Sub，
  退回单机模式

## 生命周期
- `start_ws_pubsub(app)`：在 FastAPI lifespan 启动时调用
- `stop_ws_pubsub(app)`：在 FastAPI lifespan 关闭时调用
- 通知 broker 挂在 `app.state.ws_broker`
- 聊天 broker 挂在 `app.state.ws_chat_broker`
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any, Optional
from uuid import UUID

from fastapi import FastAPI, WebSocket

logger = logging.getLogger(__name__)

DEFAULT_CHANNEL = "yiluan:ws:notifications"
DEFAULT_CHAT_CHANNEL = "yiluan:ws:chat"


class WsPubSubBroker:
    """WebSocket 广播器：本地投递 + 可选 Redis Pub/Sub 跨副本 fanout。

    通用实现：key 可以是 user_id（通知）或 order_id（聊天房间）。

    使用方式（在 endpoint 里）：
        broker = get_ws_broker()
        await broker.register(key, websocket)
        try:
            # 保持连接、收心跳...
        finally:
            await broker.unregister(key, websocket)

    业务代码推送：
        await broker.push_to_key(key, payload)    # 自动本地 + publish

    兼容别名：`push_to_user` 保留给通知场景；聊天场景请使用 `publish_to_room`。
    """

    def __init__(
        self,
        redis_client=None,
        *,
        channel: str = DEFAULT_CHANNEL,
        enabled: bool = True,
        instance_id: Optional[str] = None,
        key_field: str = "user_id",
    ):
        self.redis = redis_client
        self.channel = channel
        self.enabled = enabled
        self.instance_id = instance_id or f"{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.key_field = key_field  # "user_id"（通知）| "order_id"（聊天）

        self._local: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

        self._pubsub = None
        self._listen_task: Optional[asyncio.Task] = None
        self._started = False

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """启动订阅监听。失败时退化为单机模式（日志告警），不抛异常。"""
        if self._started:
            return
        self._started = True

        if not self.enabled or self.redis is None:
            logger.info(
                "WsPubSubBroker started in single-instance mode "
                "(channel=%s, enabled=%s, redis=%s)",
                self.channel,
                self.enabled,
                self.redis is not None,
            )
            return

        try:
            # redis.asyncio.Redis.pubsub() 是同步方法，返回 PubSub 对象
            self._pubsub = self.redis.pubsub()
            await self._pubsub.subscribe(self.channel)
            self._listen_task = asyncio.create_task(
                self._listen_loop(), name=f"ws-pubsub-listener-{self.channel}"
            )
            logger.info(
                "WsPubSubBroker started (channel=%s, instance=%s)",
                self.channel,
                self.instance_id,
            )
        except Exception as exc:
            logger.warning(
                "WsPubSubBroker failed to subscribe (channel=%s), "
                "falling back to single-instance mode: %s",
                self.channel,
                exc,
            )
            self._pubsub = None
            self._listen_task = None

    async def stop(self) -> None:
        """停止订阅监听并释放资源。"""
        if not self._started:
            return
        self._started = False

        task = self._listen_task
        self._listen_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(self.channel)
            except Exception as exc:
                logger.debug("WsPubSubBroker unsubscribe error: %s", exc)
            try:
                await self._pubsub.close()
            except Exception as exc:
                logger.debug("WsPubSubBroker pubsub close error: %s", exc)
            self._pubsub = None

        logger.info("WsPubSubBroker stopped (channel=%s)", self.channel)

    # ------------------------------------------------------------------
    # 本地连接注册
    # ------------------------------------------------------------------
    async def register(self, key: UUID | str, websocket: WebSocket) -> None:
        k = str(key)
        async with self._lock:
            self._local.setdefault(k, []).append(websocket)

    async def register_with_cap(
        self,
        key: UUID | str,
        websocket: WebSocket,
        max_connections: int,
    ) -> list[WebSocket]:
        """Register 与「踢最老」策略绑定。

        D-020：同一 key 连接数超过 ``max_connections`` 时，挤掉最早的连接（以 list
        顶部为旧）。返回被挤下的 WebSocket 列表（调用方负责 close）。

        - ``max_connections <= 0``：等价于普通 register（不限制）。
        - 同一 key 存在多个行→交给调用方串行 close，避免占用锁 await。
        """
        k = str(key)
        to_evict: list[WebSocket] = []
        async with self._lock:
            conns = self._local.setdefault(k, [])
            conns.append(websocket)
            if max_connections and len(conns) > max_connections:
                # 踢最老的（list[0]）直到基数下降到限制
                overflow = len(conns) - max_connections
                to_evict = conns[:overflow]
                self._local[k] = conns[overflow:]
        return to_evict

    async def unregister(self, key: UUID | str, websocket: WebSocket) -> None:
        k = str(key)
        async with self._lock:
            if k in self._local:
                self._local[k] = [w for w in self._local[k] if w is not websocket]
                if not self._local[k]:
                    del self._local[k]

    def local_connection_count(self, key: UUID | str | None = None) -> int:
        if key is None:
            return sum(len(v) for v in self._local.values())
        return len(self._local.get(str(key), []))

    # ------------------------------------------------------------------
    # 推送
    # ------------------------------------------------------------------
    async def push_to_key(self, key: UUID | str, payload: dict[str, Any]) -> None:
        """对单个 key（user_id 或 order_id）推送消息。

        - 同步本地投递（连接在本副本 → 立即到达）
        - 同时 publish 到 Redis 频道 → 其他副本上的连接也会收到（通过 listen loop）
        - Redis publish 失败不影响本地投递
        """
        k = str(key)

        # 1) 本地投递（无论 pubsub 是否启用，本机连接都要送达）
        await self._deliver_local(k, payload)

        # 2) publish 到其他副本
        if self.enabled and self.redis is not None and self._pubsub is not None:
            envelope = {
                "origin": self.instance_id,
                self.key_field: k,
                "payload": payload,
            }
            try:
                await self.redis.publish(self.channel, json.dumps(envelope))
            except Exception as exc:
                logger.warning(
                    "WsPubSubBroker publish failed (channel=%s, "
                    "best-effort, local already delivered): %s",
                    self.channel,
                    exc,
                )

    # 兼容别名：老代码 / 通知场景继续使用 push_to_user
    async def push_to_user(self, user_id: UUID | str, payload: dict[str, Any]) -> None:
        await self.push_to_key(user_id, payload)

    # 聊天场景推荐入口，语义更清晰
    async def publish_to_room(
        self, order_id: UUID | str, payload: dict[str, Any]
    ) -> None:
        await self.push_to_key(order_id, payload)

    async def _deliver_local(self, key: str, payload: dict[str, Any]) -> None:
        connections = list(self._local.get(key, []))
        if not connections:
            return
        text = json.dumps(payload)
        for ws in connections:
            try:
                await ws.send_text(text)
            except Exception:
                # 单个连接发送失败不影响其他连接
                pass

    # ------------------------------------------------------------------
    # 监听循环：处理其他副本 publish 来的消息
    # ------------------------------------------------------------------
    async def _listen_loop(self) -> None:
        assert self._pubsub is not None
        try:
            async for message in self._pubsub.listen():
                if not self._started:
                    break
                if message is None:
                    continue
                if message.get("type") != "message":
                    continue
                data = message.get("data")
                if data is None:
                    continue
                try:
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    envelope = json.loads(data)
                except Exception as exc:
                    logger.warning(
                        "WsPubSubBroker drop malformed message (channel=%s): %s",
                        self.channel,
                        exc,
                    )
                    continue

                origin = envelope.get("origin")
                if origin == self.instance_id:
                    # 本机 push_to_key 产生的自回显 → 已本地投递过，跳过
                    continue

                # 兼容两种 key_field；优先使用 broker 配置的，fallback 到对端
                key = envelope.get(self.key_field)
                if key is None:
                    # 兼容旧格式（user_id）或交叉格式
                    key = envelope.get("user_id") or envelope.get("order_id")
                payload = envelope.get("payload")
                if not key or payload is None:
                    continue
                await self._deliver_local(str(key), payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "WsPubSubBroker listen loop crashed (channel=%s): %s",
                self.channel,
                exc,
            )


# ---------------------------------------------------------------------------
# FastAPI lifespan helpers
# ---------------------------------------------------------------------------
# 模块级单例：
# - `_current_broker`：通知广播器（兼容 D-019 原有引用点，如 NotificationService）
# - `_current_chat_broker`：聊天房间广播器（新增，聊天 endpoint 使用）
_current_broker: Optional["WsPubSubBroker"] = None
_current_chat_broker: Optional["WsPubSubBroker"] = None


def get_current_broker() -> Optional["WsPubSubBroker"]:
    return _current_broker


def get_current_chat_broker() -> Optional["WsPubSubBroker"]:
    return _current_chat_broker


async def start_ws_pubsub(app: FastAPI, *, enabled: bool, channel: str) -> WsPubSubBroker:
    """创建并启动通知 broker，挂到 `app.state.ws_broker`。"""
    global _current_broker
    redis_client = getattr(app.state, "redis", None)
    broker = WsPubSubBroker(
        redis_client=redis_client,
        channel=channel,
        enabled=enabled,
        key_field="user_id",
    )
    await broker.start()
    app.state.ws_broker = broker
    _current_broker = broker
    return broker


async def start_ws_chat_pubsub(
    app: FastAPI, *, enabled: bool, channel: str
) -> WsPubSubBroker:
    """创建并启动聊天房间 broker，挂到 `app.state.ws_chat_broker`。"""
    global _current_chat_broker
    redis_client = getattr(app.state, "redis", None)
    broker = WsPubSubBroker(
        redis_client=redis_client,
        channel=channel,
        enabled=enabled,
        key_field="order_id",
    )
    await broker.start()
    app.state.ws_chat_broker = broker
    _current_chat_broker = broker
    return broker


async def stop_ws_pubsub(app: FastAPI) -> None:
    global _current_broker
    broker: Optional[WsPubSubBroker] = getattr(app.state, "ws_broker", None)
    if broker is not None:
        await broker.stop()
        app.state.ws_broker = None
    if _current_broker is broker:
        _current_broker = None


async def stop_ws_chat_pubsub(app: FastAPI) -> None:
    global _current_chat_broker
    broker: Optional[WsPubSubBroker] = getattr(app.state, "ws_chat_broker", None)
    if broker is not None:
        await broker.stop()
        app.state.ws_chat_broker = None
    if _current_chat_broker is broker:
        _current_chat_broker = None


def get_ws_broker_from_app(app: FastAPI) -> Optional[WsPubSubBroker]:
    return getattr(app.state, "ws_broker", None)


def get_ws_chat_broker_from_app(app: FastAPI) -> Optional[WsPubSubBroker]:
    return getattr(app.state, "ws_chat_broker", None)
