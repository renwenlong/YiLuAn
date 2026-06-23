"""Tests for S3-DEV-002-HOT-RELOAD AI blocklist pub/sub hot reload.

# Coverage map

- AC#1: POST /admin/ai-blocklist/reload admin JWT + audit_log + metric
- AC#2: subscriber 启动 + listen channel + on_event reload + success metric
- AC#3: reload 失败 metric (load_blocklist raise 时 incr failed)
- AC#4: 两副本 ≤5s 传播 — 单元测 mock pub/sub; 真集成测在 S3-TEST-002
- AC#5: 文档 + 集成测留刻晴

注: 真 redis pub/sub 测在 S3-TEST-002 staging stack; 本测仅 unit fixture (mock redis).
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.ai_blocklist_pubsub import (
    AI_BLOCKLIST_RELOAD_CHANNEL,
    AIBlocklistReloadSubscriber,
    _on_reload_event,
    get_instance_id,
)

# ---------------------------------------------------------------------------
# AC#2: subscriber start + listen + on_event reload
# ---------------------------------------------------------------------------


class TestSubscriberLifecycle:
    """订阅器启停 + idempotent."""

    @pytest.mark.asyncio
    async def test_start_without_redis_no_op(self):
        """redis client = None → start() 不 raise, subscriber 不启动."""
        sub = AIBlocklistReloadSubscriber(redis_client=None)
        await sub.start()
        assert sub._task is None  # 未起 task

    @pytest.mark.asyncio
    async def test_start_with_redis_creates_task(self):
        """有 redis client → subscriber 启动 background task."""
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_redis = MagicMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis)
        await sub.start()
        assert sub._task is not None
        assert not sub._task.done()
        # 验 subscribe 被调
        mock_pubsub.subscribe.assert_awaited_once_with(AI_BLOCKLIST_RELOAD_CHANNEL)
        # 清理
        await sub.stop()
        assert sub._task is None

    @pytest.mark.asyncio
    async def test_start_idempotent(self):
        """重复 start 不重复订阅."""
        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value=None)
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        mock_redis = MagicMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis)
        await sub.start()
        first_task = sub._task
        await sub.start()  # 第二次, no-op
        assert sub._task is first_task
        assert mock_pubsub.subscribe.await_count == 1
        await sub.stop()


# ---------------------------------------------------------------------------
# AC#3 + on_reload_event logic
# ---------------------------------------------------------------------------


def _metric_value(counter, **labels) -> float:
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


class TestOnReloadEvent:
    """_on_reload_event: load_blocklist 成功 / 失败 metric."""

    @pytest.mark.asyncio
    async def test_success_increments_success_metric(self, monkeypatch):
        """load_blocklist 不 raise → success metric incr."""
        from app.services import ai_blocklist_pubsub as mod
        from app.utils.metrics import ai_blocklist_reload_success_total

        instance = get_instance_id()
        baseline = _metric_value(
            ai_blocklist_reload_success_total, instance=instance
        )

        # Mock load_blocklist to no-op success
        monkeypatch.setattr(mod, "load_blocklist", lambda: None)

        payload = {
            "version": "test-1.0",
            "triggered_by_admin_id": "admin_42",
            "triggered_at": "2026-06-08T15:30:00Z",
        }
        await _on_reload_event(payload)

        after = _metric_value(
            ai_blocklist_reload_success_total, instance=instance
        )
        assert after - baseline == pytest.approx(1.0)

    @pytest.mark.asyncio
    async def test_failure_increments_failed_metric(self, monkeypatch):
        """load_blocklist raise → failed metric incr (reason=ExceptionName)."""
        from app.services import ai_blocklist_pubsub as mod
        from app.utils.metrics import ai_blocklist_reload_failed_total

        instance = get_instance_id()

        def _raise():
            raise RuntimeError("yml parse error simulated")

        monkeypatch.setattr(mod, "load_blocklist", _raise)

        baseline = _metric_value(
            ai_blocklist_reload_failed_total,
            instance=instance,
            reason="RuntimeError",
        )

        payload = {
            "version": "test-bad",
            "triggered_by_admin_id": "admin_42",
            "triggered_at": "2026-06-08T15:30:00Z",
        }
        await _on_reload_event(payload)

        after = _metric_value(
            ai_blocklist_reload_failed_total,
            instance=instance,
            reason="RuntimeError",
        )
        assert after - baseline == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# AC#2 + AC#4: subscriber 收事件 → 调 _on_reload_event
# ---------------------------------------------------------------------------


class TestSubscriberMessageHandling:
    """subscriber 收 pub/sub 消息后 dispatch."""

    @pytest.mark.asyncio
    async def test_subscriber_dispatches_valid_payload(self, monkeypatch):
        """收 message → 调 _on_reload_event."""
        from app.services import ai_blocklist_pubsub as mod

        on_event_calls = []

        async def _capture_event(payload):
            on_event_calls.append(payload)

        monkeypatch.setattr(mod, "_on_reload_event", _capture_event)

        # Mock pubsub message queue: first 返一条 reload event, 后续 None
        msgs = [
            {
                "type": "message",
                "data": json.dumps(
                    {"version": "v1", "triggered_by_admin_id": "a1"}
                ).encode("utf-8"),
            },
            None,
        ]

        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        # get_message: 第一次返 msgs[0], 后续 None
        get_message_calls = iter(msgs)

        async def _get_message(**kwargs):
            try:
                return next(get_message_calls)
            except StopIteration:
                # 让 loop yield + cancel 生效
                await asyncio.sleep(0.05)
                return None

        mock_pubsub.get_message = _get_message
        mock_redis = MagicMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis)
        await sub.start()
        # 给 loop 几个 tick 跑
        await asyncio.sleep(0.1)
        await sub.stop()

        assert len(on_event_calls) == 1
        assert on_event_calls[0]["version"] == "v1"
        assert on_event_calls[0]["triggered_by_admin_id"] == "a1"

    @pytest.mark.asyncio
    async def test_subscriber_ignores_invalid_json(self, monkeypatch):
        """收非 JSON message → log warning, 不调 _on_reload_event."""
        from app.services import ai_blocklist_pubsub as mod

        on_event_calls = []

        async def _capture_event(payload):
            on_event_calls.append(payload)

        monkeypatch.setattr(mod, "_on_reload_event", _capture_event)

        msgs = [
            {"type": "message", "data": b"not-json{{{"},
            None,
        ]

        mock_pubsub = MagicMock()
        mock_pubsub.subscribe = AsyncMock()
        mock_pubsub.unsubscribe = AsyncMock()
        mock_pubsub.close = AsyncMock()
        get_message_calls = iter(msgs)

        async def _get_message(**kwargs):
            try:
                return next(get_message_calls)
            except StopIteration:
                # 让 loop yield + cancel 生效
                await asyncio.sleep(0.05)
                return None

        mock_pubsub.get_message = _get_message
        mock_redis = MagicMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)

        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis)
        await sub.start()
        await asyncio.sleep(0.1)
        await sub.stop()

        assert on_event_calls == []  # invalid JSON 不 dispatch


class TestInstanceID:
    """get_instance_id: HOSTNAME → gethostname → 'unknown'."""

    def test_hostname_env_priority(self, monkeypatch):
        monkeypatch.setenv("HOSTNAME", "test-pod-1")
        assert get_instance_id() == "test-pod-1"

    def test_fallback_to_gethostname(self, monkeypatch):
        monkeypatch.delenv("HOSTNAME", raising=False)
        # gethostname 不 raise (本机 always 有 hostname)
        result = get_instance_id()
        assert result != "unknown"  # 真机有 hostname
        assert len(result) > 0


# ---------------------------------------------------------------------------
# S3-OPS-AI-BLOCKLIST-SUBSCRIBER-WATCHDOG
# AC#1/#2/#3: watchdog 检 _loop task 死亡 → restart + metric
# ---------------------------------------------------------------------------


def _make_mock_redis():
    """构造一个 mock redis, 其 pubsub.get_message 永远返 None (loop 空转不退出)。"""
    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.get_message = AsyncMock(return_value=None)
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.close = AsyncMock()
    mock_redis = MagicMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    return mock_redis, mock_pubsub


class TestSubscriberWatchdog:
    """S3-OPS-AI-BLOCKLIST-SUBSCRIBER-WATCHDOG: crash detect + restart."""

    @pytest.mark.asyncio
    async def test_watchdog_task_starts_with_subscriber(self):
        """AC#1: start() 同时拉起 watchdog task。"""
        mock_redis, _ = _make_mock_redis()
        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis, watchdog_interval=0.05)
        await sub.start()
        try:
            assert sub._watchdog_task is not None
            assert not sub._watchdog_task.done()
        finally:
            await sub.stop()
        # stop 后 watchdog 也清理
        assert sub._watchdog_task is None

    @pytest.mark.asyncio
    async def test_watchdog_restarts_crashed_loop(self):
        """AC#3 核心: _loop task 被强制 crash → watchdog detect + restart + 新 task 活。"""
        mock_redis, _ = _make_mock_redis()
        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis, watchdog_interval=0.05)
        await sub.start()
        try:
            original_task = sub._task
            assert original_task is not None and not original_task.done()

            # 模拟 crash: 直接 cancel _loop task (绕过 stop, 不设 _stop_event)。
            # watchdog 应检到 _task.done() 且 _stop_event 未设 → 重启。
            sub._task.cancel()
            await asyncio.sleep(0)  # 让 cancel 生效
            assert sub._task.done()

            # 等 watchdog 跑至少一轮 (interval 0.05s) + restart。
            for _ in range(40):  # 最多 ~2s
                await asyncio.sleep(0.05)
                if (
                    sub._task is not None
                    and not sub._task.done()
                    and sub._task is not original_task
                ):
                    break

            # 验证: 新 _task 被拉起, 不是原来那个 (已 crash 的)。
            assert sub._task is not None, "watchdog 未重启 _task"
            assert not sub._task.done(), "重启的 _task 不该立刻 done"
            assert sub._task is not original_task, "应是新 task 而非原 crashed task"
            # subscribe 被再次调用 (restart 重新订阅)。
            assert mock_redis.pubsub.call_count >= 2
        finally:
            await sub.stop()

    @pytest.mark.asyncio
    async def test_watchdog_restart_increments_metric(self, monkeypatch):
        """AC#2: restart 写 ai_blocklist_subscriber_restart_total metric。"""
        from app.utils import metrics as metrics_mod

        inc_calls = []

        class _FakeMetric:
            def labels(self, **kwargs):
                inc_calls.append(kwargs)
                return self

            def inc(self):
                pass

        monkeypatch.setattr(
            metrics_mod, "ai_blocklist_subscriber_restart_total", _FakeMetric()
        )

        mock_redis, _ = _make_mock_redis()
        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis, watchdog_interval=0.05)
        await sub.start()
        try:
            original_task = sub._task
            sub._task.cancel()
            await asyncio.sleep(0)

            for _ in range(40):
                await asyncio.sleep(0.05)
                if (
                    sub._task is not None
                    and not sub._task.done()
                    and sub._task is not original_task
                ):
                    break

            # metric 至少被 inc 一次, reason=task_crashed (cancel 导致 done)。
            assert len(inc_calls) >= 1, "restart metric 未 inc"
            reasons = {c.get("reason") for c in inc_calls}
            assert "task_crashed" in reasons, f"reason 应含 task_crashed, got {reasons}"
        finally:
            await sub.stop()

    @pytest.mark.asyncio
    async def test_watchdog_does_not_restart_after_stop(self):
        """AC#1 边界: stop() 后 watchdog 不该再重启 (主动停止 != crash)。"""
        mock_redis, _ = _make_mock_redis()
        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis, watchdog_interval=0.05)
        await sub.start()
        await sub.stop()

        # stop 后 _task / watchdog 都应清理为 None。
        assert sub._task is None
        assert sub._watchdog_task is None

        # 再等几个 interval, 确认没有任何 task 被偷偷重启。
        await asyncio.sleep(0.2)
        assert sub._task is None, "stop 后 watchdog 不该重启 _task"
        assert sub._watchdog_task is None

    @pytest.mark.asyncio
    async def test_watchdog_idempotent_ensure(self):
        """AC#1: 重复调 start() 不重复创建 watchdog (idempotent)。"""
        mock_redis, _ = _make_mock_redis()
        sub = AIBlocklistReloadSubscriber(redis_client=mock_redis, watchdog_interval=0.05)
        await sub.start()
        try:
            wd1 = sub._watchdog_task
            await sub.start()  # 第二次 start (idempotent)
            wd2 = sub._watchdog_task
            # watchdog task 应是同一个 (没被重复创建)。
            assert wd1 is wd2
        finally:
            await sub.stop()
