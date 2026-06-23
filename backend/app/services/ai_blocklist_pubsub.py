"""AI blocklist Redis pub/sub hot reload subscriber.

[S3-DEV-002-HOT-RELOAD / ADR-0048 §4.1 + 刻晴 review #5]

# 背景

PR #221 KEYWORD-FILTER backend MVP 完成时 yml 仅 import-time auto-load,
yml 改后必须 backend 进程重启或 rolling deploy 才生效, 多副本灰度场景
admin trigger 后**无法秒级生效**.

本模块加 Redis pub/sub subscriber: backend 启动启 subscriber, 监听
``ai_blocklist_reload`` topic; admin 调 POST /admin/ai-blocklist/reload
publish 事件 → 所有副本 subscriber 收到 → 调 ``load_blocklist()`` 重 init
cache. **PRD-003 v0.3 §7 灰度监控**: 两副本 ≤5s 内 ``/debug/ai-blocklist-version``
返回新 version.

# 架构 (镜 ws/pubsub.py 但简化, 无 WebSocket 状态管理)

```
[admin trigger]
    POST /admin/ai-blocklist/reload
        |
        v
    handler:
        - 写 admin_audit_logs action=ai_blocklist_reload
        - metric ai_blocklist_reload_triggered_total{admin_id}.inc()
        - publish redis CHANNEL_NAME {"version": <git_commit>, "triggered_by": <admin_id>, ...}
        - 返 202 Accepted (不等待传播; 全副本 ≤5s 是 SLA)

[每副本 backend startup]
    start_ai_blocklist_reload_subscriber(app):
        - 启 async task: subscribe(CHANNEL_NAME)
        - 收事件 → ai_prep_filter.load_blocklist() 重 init
        - 成功 → metric ai_blocklist_reload_success_total{instance=hostname}.inc()
        - 失败 → metric ai_blocklist_reload_failed_total{instance, reason}.inc() + log error
```

# 降级策略

- ``settings.ai_blocklist_pubsub_enabled = False`` → subscriber 不启, admin
  trigger publish 仍走但无消费方 (rolling deploy 是 fallback)
- Redis 不可用 → subscriber 启动失败记 log + warning metric, 不阻 boot;
  rolling deploy 重启 backend 也能 reload yml (cold fallback)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any, Optional

from fastapi import FastAPI

from app.config import settings
from app.services.ai_prep_filter import load_blocklist

logger = logging.getLogger("app.cron.ai_blocklist_pubsub")

# Redis channel name for pub/sub topic.
AI_BLOCKLIST_RELOAD_CHANNEL = "yiluan:ai-blocklist:reload"


def get_instance_id() -> str:
    """Backend 实例标识 (用于 metric label).

    优先级: HOSTNAME env (K8s/Docker pod name) → socket.gethostname() → "unknown".
    """
    return os.getenv("HOSTNAME") or socket.gethostname() or "unknown"


async def _on_reload_event(payload: dict[str, Any]) -> None:
    """Handle one reload event: re-load yml + 写 metric.

    Payload schema (admin trigger publish 时构造):
        {
            "version": "<git_commit_hash 或 timestamp>",
            "triggered_by_admin_id": "<admin_id>",
            "triggered_at": "<ISO8601>"
        }
    """
    instance_id = get_instance_id()
    triggered_by = payload.get("triggered_by_admin_id", "?")
    version_hint = payload.get("version", "?")

    try:
        load_blocklist()
        try:
            from app.utils.metrics import ai_blocklist_reload_success_total

            ai_blocklist_reload_success_total.labels(instance=instance_id).inc()
        except Exception:  # pragma: no cover
            logger.exception("ai_blocklist_reload_success_total inc failed")
        logger.info(
            "ai_blocklist reload OK: instance=%s triggered_by=%s version=%s",
            instance_id,
            triggered_by,
            version_hint,
        )
    except Exception as exc:
        reason = type(exc).__name__
        try:
            from app.utils.metrics import ai_blocklist_reload_failed_total

            ai_blocklist_reload_failed_total.labels(
                instance=instance_id, reason=reason
            ).inc()
        except Exception:  # pragma: no cover
            logger.exception("ai_blocklist_reload_failed_total inc failed")
        logger.error(
            "ai_blocklist reload FAILED: instance=%s reason=%s triggered_by=%s",
            instance_id,
            reason,
            triggered_by,
            exc_info=exc,
        )


class AIBlocklistReloadSubscriber:
    """Async Redis pub/sub subscriber - lightweight, no state.

    生命周期管理:
    - ``start(app)``: 启动 async background task, 订阅 CHANNEL_NAME
    - ``stop()``: 取消 task + 关闭 pubsub connection

    Idempotent: 重复 start 不重复订阅 (检 ``_task`` 是否 active).
    """

    def __init__(self, redis_client: Any = None, watchdog_interval: float = 30.0) -> None:
        self._redis = redis_client
        self._task: Optional[asyncio.Task] = None
        self._pubsub: Any = None
        self._stop_event: asyncio.Event = asyncio.Event()
        # S3-OPS-AI-BLOCKLIST-SUBSCRIBER-WATCHDOG: watchdog 周期检 _loop task 是否死亡。
        self._watchdog_task: Optional[asyncio.Task] = None
        self._watchdog_interval: float = watchdog_interval

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            logger.debug("AIBlocklistReloadSubscriber already running, skip")
            return

        if self._redis is None:
            logger.warning(
                "AIBlocklistReloadSubscriber: no redis client, "
                "subscriber will not start (cold fallback via rolling deploy)"
            )
            return

        try:
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(AI_BLOCKLIST_RELOAD_CHANNEL)
        except Exception as exc:  # pragma: no cover - redis connect issue
            logger.error(
                "AIBlocklistReloadSubscriber: subscribe failed, "
                "subscriber not started: %s",
                exc,
                exc_info=exc,
            )
            return

        self._stop_event.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info(
            "AIBlocklistReloadSubscriber started: channel=%s instance=%s",
            AI_BLOCKLIST_RELOAD_CHANNEL,
            get_instance_id(),
        )
        # 启动 watchdog (idempotent): 守护 _loop task, crash 后自动重启。
        self._ensure_watchdog()

    def _ensure_watchdog(self) -> None:
        """启动 watchdog task (idempotent)。

        watchdog 独立于 _loop task: 即便 _loop crash, watchdog 仍存活并负责重启它。
        仅当 watchdog 未运行时才创建, 避免重复。
        """
        if self._watchdog_task is not None and not self._watchdog_task.done():
            return
        self._watchdog_task = asyncio.create_task(self._watchdog_loop())
        logger.debug(
            "AIBlocklistReloadSubscriber watchdog started: interval=%ss",
            self._watchdog_interval,
        )

    async def _watchdog_loop(self) -> None:
        """周期检 _loop task 是否死亡, 死了就重启 (AC#1)。

        重启条件: ``_stop_event`` 未设 (非主动 stop) 且 ``_task`` 缺失/done。
        区分两种死因写 metric (AC#2):
            - task_missing : _task is None (start 未拉起 / 被清空)
            - task_crashed : _task.done() (loop 抛未捕获异常退出)
        watchdog 自身异常被吞 + sleep 后继续, 不让 watchdog 自己挂掉。
        """
        while not self._stop_event.is_set():
            try:
                await asyncio.sleep(self._watchdog_interval)
            except asyncio.CancelledError:
                raise
            if self._stop_event.is_set():
                break
            try:
                # _task 缺失或已结束 = 需要重启 (排除主动 stop, 上面已 break)。
                task_dead = self._task is None or self._task.done()
                if not task_dead:
                    continue
                reason = "task_missing" if self._task is None else "task_crashed"
                logger.warning(
                    "AIBlocklistReloadSubscriber watchdog: _loop task dead "
                    "(reason=%s), restarting; instance=%s",
                    reason,
                    get_instance_id(),
                )
                # 清空死 task + 旧 pubsub, 让 start() 重新 subscribe。
                self._task = None
                if self._pubsub is not None:
                    try:
                        await self._pubsub.close()
                    except Exception:  # pragma: no cover
                        pass
                    self._pubsub = None
                await self.start()
                # 重启成功 (拉起新 _task) 才计数。
                if self._task is not None and not self._task.done():
                    try:
                        from app.utils.metrics import (
                            ai_blocklist_subscriber_restart_total,
                        )

                        ai_blocklist_subscriber_restart_total.labels(
                            instance=get_instance_id(), reason=reason
                        ).inc()
                    except Exception:  # pragma: no cover
                        logger.exception(
                            "ai_blocklist_subscriber_restart_total inc failed"
                        )
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # pragma: no cover - watchdog 自身必须存活
                logger.exception(
                    "AIBlocklistReloadSubscriber watchdog iteration error: %s", exc
                )

    async def _loop(self) -> None:
        if self._pubsub is None:
            return
        try:
            while not self._stop_event.is_set():
                try:
                    msg = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0,
                    )
                except Exception as exc:
                    logger.warning(
                        "AIBlocklistReloadSubscriber: get_message error: %s", exc
                    )
                    await asyncio.sleep(0.5)
                    continue

                if msg is None or msg.get("type") != "message":
                    continue

                raw = msg.get("data")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    logger.warning(
                        "AIBlocklistReloadSubscriber: invalid JSON payload: %r", raw
                    )
                    continue
                if not isinstance(payload, dict):
                    logger.warning(
                        "AIBlocklistReloadSubscriber: payload not dict: %r", payload
                    )
                    continue
                await _on_reload_event(payload)
        except asyncio.CancelledError:
            logger.info("AIBlocklistReloadSubscriber loop cancelled")
            raise
        except Exception as exc:  # pragma: no cover
            logger.exception("AIBlocklistReloadSubscriber loop crashed: %s", exc)

    async def stop(self) -> None:
        self._stop_event.set()
        # 先停 watchdog, 避免它在我们 cancel _loop 时误判 crash 又重启。
        if self._watchdog_task is not None:
            if not self._watchdog_task.done():
                self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except (asyncio.CancelledError, Exception):  # pragma: no cover
                pass
            self._watchdog_task = None
        # 无条件清理 _task: stop 语义 = 彻底停。注意 _loop 可能因 _stop_event
        # 已自然退出 (done), 也可能仍 running 需 cancel; 两种都要置 None。
        if self._task is not None:
            if not self._task.done():
                self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # pragma: no cover
                pass
            self._task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe(AI_BLOCKLIST_RELOAD_CHANNEL)
                await self._pubsub.close()
            except Exception:  # pragma: no cover
                pass
            self._pubsub = None
        logger.info("AIBlocklistReloadSubscriber stopped")


async def start_ai_blocklist_reload_subscriber(app: FastAPI) -> None:
    """挂到 ``app.state.ai_blocklist_reload_subscriber`` (FastAPI lifespan startup)."""
    if not getattr(settings, "ai_blocklist_pubsub_enabled", True):
        logger.info(
            "ai_blocklist_pubsub_enabled=False, subscriber not started; "
            "yml reload only via rolling deploy"
        )
        return

    redis_client = getattr(app.state, "redis", None)
    subscriber = AIBlocklistReloadSubscriber(redis_client=redis_client)
    await subscriber.start()
    app.state.ai_blocklist_reload_subscriber = subscriber


async def stop_ai_blocklist_reload_subscriber(app: FastAPI) -> None:
    """(FastAPI lifespan shutdown)."""
    subscriber: Optional[AIBlocklistReloadSubscriber] = getattr(
        app.state, "ai_blocklist_reload_subscriber", None
    )
    if subscriber is not None:
        await subscriber.stop()
        app.state.ai_blocklist_reload_subscriber = None


__all__ = [
    "AI_BLOCKLIST_RELOAD_CHANNEL",
    "AIBlocklistReloadSubscriber",
    "get_instance_id",
    "start_ai_blocklist_reload_subscriber",
    "stop_ai_blocklist_reload_subscriber",
]
