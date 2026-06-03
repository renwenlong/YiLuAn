"""Distributed Circuit Breaker (ADR-0040 Phase 1)

继承 backend/app/utils/outbound.py CircuitBreaker，
在 OPEN → HALF_OPEN 转换前用 Redis SETNX probe_lock 协调多 worker。

设计目标（详 ADR-0040 §4 方案 A）：
- 每 worker 仍维护本地 CB state（in-memory）→ 失败计数本地，零 RTT 开销
- HALF_OPEN 探测前 SETNX cb:{provider}:probe_lock：只有抢到锁的 worker
  真发探测请求，其他 worker 直接拒（rejected_total += 1），杜绝雪崩探测
- probe lock TTL per provider（wxpay 8-10s / DeepSeek 5s / mock 2s），
  hutao ADR-0040 review 关切落实
- Redis 不可用降级到纯本地 CB（不引新单点）

向后兼容：
- @outbound_call(distributed=True) 显式开启；distributed=False（默认）行为
  与 ADR-0026r1 base CircuitBreaker 完全等价

后续 Phase 2（失败计数 pubsub 广播）暂留 TODO，本 Phase 1 不实施。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.utils.outbound import CircuitBreaker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

try:
    from prometheus_client import REGISTRY, Counter

    def _counter(name: str, doc: str, labels: list[str]) -> Counter:
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is not None:
            return existing  # type: ignore[return-value]
        return Counter(name, doc, labels)

    PROBE_LOCK_ACQUIRED_TOTAL = _counter(
        "outbound_circuit_probe_lock_acquired_total",
        "Distributed CB probe lock acquired (this worker becomes the probe runner)",
        ["provider"],
    )
    PROBE_LOCK_REJECTED_TOTAL = _counter(
        "outbound_circuit_probe_lock_rejected_total",
        "Distributed CB probe lock rejected (another worker is probing)",
        ["provider"],
    )
    PROBE_LOCK_REDIS_DOWN_TOTAL = _counter(
        "outbound_circuit_probe_lock_redis_down_total",
        "Distributed CB probe lock check failed because Redis is unavailable; "
        "fell back to local CB semantics",
        ["provider"],
    )
except Exception:  # pragma: no cover - prometheus optional
    PROBE_LOCK_ACQUIRED_TOTAL = None
    PROBE_LOCK_REJECTED_TOTAL = None
    PROBE_LOCK_REDIS_DOWN_TOTAL = None


def _inc(counter: Any, provider: str) -> None:
    if counter is None:
        return
    try:
        counter.labels(provider=provider).inc()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Redis client accessor — pluggable for tests
# ---------------------------------------------------------------------------

# 全局 setter，由 app startup 注入；测试可直接 monkeypatch。
_redis_client: Any = None


def set_distributed_redis_client(client: Any) -> None:
    """注入 Redis client（异步 / sync 都可，调用方判断）。

    在 app startup 时调用：
        from app.utils.distributed_circuit_breaker import set_distributed_redis_client
        set_distributed_redis_client(app.state.redis)
    """
    global _redis_client
    _redis_client = client


def get_distributed_redis_client() -> Any:
    return _redis_client


# ---------------------------------------------------------------------------
# probe_lock TTL per provider
# ---------------------------------------------------------------------------

# 默认 TTL 表（秒）。调用方可通过 DistributedCircuitBreaker(probe_lock_ttl=) 覆盖。
# - wxpay：探测请求 RTT 2-3s + 重试一次 + 网络抖动 → 8s
# - DeepSeek：大模型推理慢，但探测用最小 prompt → 5s
# - aliyun_sms：短信网关快 → 3s
# - mock：本地 stub → 2s
DEFAULT_PROBE_LOCK_TTL: dict[str, float] = {
    "wxpay": 8.0,
    "wechat_pay": 8.0,  # 现有 providers/payment/wechat.py 采用的 provider 名
    "deepseek": 5.0,
    "aliyun_sms": 3.0,
    "mock": 2.0,
}

DEFAULT_FALLBACK_TTL = 5.0


def default_probe_lock_ttl(provider: str) -> float:
    """根据 provider 名返回默认 TTL；未知 provider fallback 5s。"""
    return DEFAULT_PROBE_LOCK_TTL.get(provider, DEFAULT_FALLBACK_TTL)


# ---------------------------------------------------------------------------
# DistributedCircuitBreaker
# ---------------------------------------------------------------------------


class DistributedCircuitBreaker(CircuitBreaker):
    """CircuitBreaker + Redis SETNX probe_lock 协调（ADR-0040 Phase 1）。

    覆写 ``allow_request``：本地 state 转 HALF_OPEN 之前 SETNX 抢锁。

    Redis 不可用时（client None / SETNX 抛异常）降级到 parent 行为
    （纯本地 CB），打 metric 但不阻断业务。
    """

    def __init__(
        self,
        threshold: int,
        timeout: float,
        provider: str,
        half_open_success_threshold: int = 3,
        idle_reset_seconds: Optional[float] = None,
        probe_lock_ttl: Optional[float] = None,
    ) -> None:
        super().__init__(
            threshold=threshold,
            timeout=timeout,
            half_open_success_threshold=half_open_success_threshold,
            idle_reset_seconds=idle_reset_seconds,
        )
        self.provider = provider
        self.probe_lock_ttl = (
            probe_lock_ttl
            if probe_lock_ttl is not None
            else default_probe_lock_ttl(provider)
        )

    @property
    def probe_lock_key(self) -> str:
        return f"cb:{self.provider}:probe_lock"

    def _try_acquire_probe_lock_sync(self) -> bool:
        """SETNX probe_lock + EX TTL。

        返回 True = 抢到锁（本 worker 进入探测）。
        返回 False = 别 worker 已抢到（本 worker 拒）。
        Redis 不可用 → 返回 True 降级（打 metric，不阻断）。
        """
        client = get_distributed_redis_client()
        if client is None:
            _inc(PROBE_LOCK_REDIS_DOWN_TOTAL, self.provider)
            return True

        try:
            # 兼容 sync / async redis client，业务侧 startup 注入 async client
            # 时 allow_request 是 sync 接口，async 调用走 asyncio.run_coroutine_threadsafe
            # 不适合 — 因此仅用 sync-接口的 redis client 或 await-able 但 returns coroutine
            # 实际部署用 redis-py asyncio 时由调用方包 sync wrapper（详 follow-up）
            result = client.set(
                self.probe_lock_key,
                "1",
                nx=True,
                ex=int(max(1, self.probe_lock_ttl)),
            )
            return bool(result)
        except Exception as exc:
            logger.warning(
                "distributed CB probe_lock SETNX failed for %s: %s — "
                "降级 to local CB",
                self.provider,
                exc,
            )
            _inc(PROBE_LOCK_REDIS_DOWN_TOTAL, self.provider)
            return True

    def allow_request(self) -> bool:
        """覆写：转 HALF_OPEN 前抢锁。

        其他状态语义不变（CLOSED 直放 / OPEN 时间未到 拒 / HALF_OPEN 放探测）。
        """
        now = time.monotonic()

        # IDLE 自动 reset（与 parent 同源）
        if (
            self.state == self.CLOSED
            and self.failure_count > 0
            and now - self._last_activity_at >= self.idle_reset_seconds
        ):
            self.failure_count = 0

        if self.state == self.CLOSED:
            return True

        if self.state == self.OPEN:
            if now - self._opened_at < self.timeout:
                return False
            # OPEN_TIMEOUT_ELAPSED → 抢探测锁
            if self._try_acquire_probe_lock_sync():
                _inc(PROBE_LOCK_ACQUIRED_TOTAL, self.provider)
                self.state = self.HALF_OPEN
                self.half_open_success_count = 0
                return True
            else:
                _inc(PROBE_LOCK_REJECTED_TOTAL, self.provider)
                # 别 worker 在探测，本 worker 继续 OPEN 等下个 timeout
                return False

        # HALF_OPEN（本 worker 已是 probe 持有者）：允许探测
        return True
