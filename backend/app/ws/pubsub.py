"""WebSocket Redis Pub/Sub 广播器（D-019 多副本支持）。

## 背景
D-017 的 `_notification_connections` 是进程内 dict，在 K8s / ACA 多副本场景下，
一条通知只能送达"用户连接所在"的那个副本；用户连接的实例和触发通知的实例不同
时，推送就会丢失。本模块通过 Redis Pub/Sub 解决此问题。

## 架构
1. 每个副本启动时订阅统一频道 `WS_NOTIFICATIONS_CHANNEL`（默认 `yiluan:ws:notifications`）
2. 本副本维护 `_local_connections: dict[user_id, list[WebSocket]]`
3. 推送通知时：
   - **立即本地投递** + **publish 到 Redis 频道**（双通道，低延迟 + 跨副本）
4. 消息体带 `origin` 标识当前实例 ID；pubsub 监听协程收到消息时：
   - 若 `origin == self.instance_id` → 跳过（本机已投递，避免双发）
   - 否则 → 查本地表投递（其他副本产生的消息）

## 降级策略
- Redis 不可用或订阅失败 → 记录告警日志，退化为单机内存广播（best-effort）；
  业务不阻塞
- 配置开关 `WS_PUBSUB_ENABLED=False` → 完全关闭 Pub/Sub，退回单机模式

## 生命周期
- `start_ws_pubsub(app)`：在 FastAPI lifespan 启动时调用
- `stop_ws_pubsub(app)`：在 FastAPI lifespan 关闭时调用
- broker 挂在 `app.state.ws_broker`，WebSocket endpoint 和 NotificationService
  都通过 `get_ws_broker()` 取用
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


class WsPubSubBroker:
    """WebSocket 广播器：本地投递 + 可选 Redis Pub/Sub 跨副本 fanout。

    使用方式（在 endpoint 里）：
        broker = get_ws_broker()
        await broker.register(user_id, websocket)
        try:
            # 保持连接、收心跳...
        finally:
            await broker.unregister(user_id, websocket)

    业务代码推送：
        await broker.push_to_user(user_id, payload)   # 自动本地 + publish
    """

    def __init__(
        self,
        redis_client=None,
        *,
        channel: str = DEFAULT_CHANNEL,
        enabled: bool = True,
        instance_id: Optional[str] = None,
    ):
        self.redis = redis_client
        self.channel = channel
        self.enabled = enabled
        self.instance_id = instance_id or f"{os.getpid()}-{uuid.uuid4().hex[:8]}"

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
                "WsPubSubBroker started in single-instance mode (enabled=%s, redis=%s)",
                self.enabled,
                self.redis is not None,
            )
            return

        try:
            # redis.asyncio.Redis.pubsub() 是同步方法，返回 PubSub 对象
            self._pubsub = self.redis.pubsub()
            await self._pubsub.subscribe(self.channel)
            self._listen_task = asyncio.create_task(
                self._listen_loop(), name="ws-pubsub-listener"
            )
            logger.info(
                "WsPubSubBroker started (channel=%s, instance=%s)",
                self.channel,
                self.instance_id,
            )
        except Exception as exc:
            logger.warning(
                "WsPubSubBroker failed to subscribe, falling back to single-instance mode: %s",
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

        logger.info("WsPubSubBroker stopped")

    # ------------------------------------------------------------------
    # 本地连接注册
    # ------------------------------------------------------------------
    async def register(self, user_id: UUID | str, websocket: WebSocket) -> None:
        key = str(user_id)
        async with self._lock:
            self._local.setdefault(key, []).append(websocket)

    async def unregister(self, user_id: UUID | str, websocket: WebSocket) -> None:
        key = str(user_id)
        async with self._lock:
            if key in self._local:
                self._local[key] = [w for w in self._local[key] if w is not websocket]
                if not self._local[key]:
                    del self._local[key]

    def local_connection_count(self, user_id: UUID | str | None = None) -> int:
        if user_id is None:
            return sum(len(v) for v in self._local.values())
        return len(self._local.get(str(user_id), []))

    # ------------------------------------------------------------------
    # 推送
    # ------------------------------------------------------------------
    async def push_to_user(self, user_id: UUID | str, payload: dict[str, Any]) -> None:
        """对单个用户推送消息。

        - 同步本地投递（连接在本副本 → 立即到达）
        - 同时 publish 到 Redis 频道 → 其他副本上的连接也会收到（通过 listen loop）
        - Redis publish 失败不影响本地投递
        """
        key = str(user_id)

        # 1) 本地投递（无论 pubsub 是否启用，本机连接都要送达）
        await self._deliver_local(key, payload)

        # 2) publish 到其他副本
        if self.enabled and self.redis is not None and self._pubsub is not None:
            envelope = {
                "origin": self.instance_id,
                "user_id": key,
                "payload": payload,
            }
            try:
                await self.redis.publish(self.channel, json.dumps(envelope))
            except Exception as exc:
                logger.warning(
                    "WsPubSubBroker publish failed (best-effort, local already delivered): %s",
                    exc,
                )

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
                    logger.warning("WsPubSubBroker drop malformed message: %s", exc)
                    continue

                origin = envelope.get("origin")
                if origin == self.instance_id:
                    # 本机 push_to_user 产生的自回显 → 已本地投递过，跳过
                    continue

                user_id = envelope.get("user_id")
                payload = envelope.get("payload")
                if not user_id or payload is None:
                    continue
                await self._deliver_local(str(user_id), payload)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("WsPubSubBroker listen loop crashed: %s", exc)


# ---------------------------------------------------------------------------
# FastAPI lifespan helpers
# ---------------------------------------------------------------------------
# 模块级单例（仅主应用）：方便 NotificationService 等无 app 上下文的调用点取用；
# 测试中若未调用 `start_ws_pubsub` 则为 None，调用方需自己降级
_current_broker: Optional["WsPubSubBroker"] = None


def get_current_broker() -> Optional["WsPubSubBroker"]:
    return _current_broker


async def start_ws_pubsub(app: FastAPI, *, enabled: bool, channel: str) -> WsPubSubBroker:
    """创建并启动 broker，挂到 `app.state.ws_broker`。"""
    global _current_broker
    redis_client = getattr(app.state, "redis", None)
    broker = WsPubSubBroker(
        redis_client=redis_client,
        channel=channel,
        enabled=enabled,
    )
    await broker.start()
    app.state.ws_broker = broker
    _current_broker = broker
    return broker


async def stop_ws_pubsub(app: FastAPI) -> None:
    global _current_broker
    broker: Optional[WsPubSubBroker] = getattr(app.state, "ws_broker", None)
    if broker is not None:
        await broker.stop()
        app.state.ws_broker = None
    if _current_broker is broker:
        _current_broker = None


def get_ws_broker_from_app(app: FastAPI) -> Optional[WsPubSubBroker]:
    return getattr(app.state, "ws_broker", None)
