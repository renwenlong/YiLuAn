"""分布式锁实现（D-018 生产级升级）。

提供两种实现，通过工厂函数 `acquire_scheduler_lock` 按数据库方言自动选择：

1. `PostgresAdvisoryLock`（**生产主路径**）
   - 使用 PostgreSQL 的 `pg_try_advisory_lock(bigint)` / `pg_advisory_unlock(bigint)`
   - 强一致、由数据库原生保证：即便客户端崩溃，锁也会随连接关闭自动释放
   - 无需额外依赖（已强依赖 PG）
   - 关键点：lock/unlock 必须在**同一数据库连接**上发起。我们通过
     `AsyncSession.connection()` 拿到 `AsyncConnection`，并在整个临界区持有同一
     `AsyncSession`，确保 pool 不会中途把连接换出。

2. `RedisNXLock`（**非 PG 退化/测试**）
   - 保留原有 `SET NX EX` best-effort 语义
   - 适用于本地开发（若使用 SQLite）、单元测试、以及 PG 暂不可用时降级

选择策略（`acquire_scheduler_lock`）：
- 如果传入的 `session` 底层方言为 `postgresql` → 使用 `PostgresAdvisoryLock`
- 否则若有可用 `redis_client` → 使用 `RedisNXLock`
- 否则退化为"假锁"（总是成功获取），保证任务不会完全停摆

异常策略：
- 任何锁相关异常都不应击穿调度器，`__aenter__` 失败时返回未获取状态，让调度器跳过本轮。
"""
from __future__ import annotations

import hashlib
import logging
from typing import Optional, Protocol

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------
class DistributedLock(Protocol):
    acquired: bool

    async def __aenter__(self) -> "DistributedLock": ...
    async def __aexit__(self, exc_type, exc, tb) -> None: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def lock_key_to_bigint(key: str) -> int:
    """把字符串 key 稳定映射到 PG advisory lock 所需的 bigint。

    - 使用 sha1 的前 8 字节并转换为 signed 64-bit
    - 稳定、碰撞概率极低；不同 key 得到不同锁
    """
    digest = hashlib.sha1(key.encode("utf-8")).digest()[:8]
    unsigned = int.from_bytes(digest, byteorder="big", signed=False)
    # 转为 signed int64 范围
    if unsigned >= 2**63:
        unsigned -= 2**64
    return unsigned


def _session_dialect(session: AsyncSession) -> str:
    try:
        bind = session.get_bind()
        return bind.dialect.name  # 'postgresql' / 'sqlite' / ...
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# PostgresAdvisoryLock
# ---------------------------------------------------------------------------
class PostgresAdvisoryLock:
    """PostgreSQL session-level advisory lock.

    使用说明：
      async with PostgresAdvisoryLock(session, "yiluan:scheduler:xxx") as lock:
          if lock.acquired:
              ... # 临界区
          else:
              ... # 其他实例持有

    注意事项：
      - `session` 必须在整个 `with` 块中保持活跃，不要在其中 commit/close。
        （调度器任务内部已确保此语义：我们在同一个 `async with async_session()`
         作用域内同时持锁与工作。）
      - PG advisory lock 是 session-scoped（= 连接级）。即便忘记 unlock，只要
        连接归还/断开，锁也会自动释放，不会僵死。
    """

    def __init__(self, session: AsyncSession, key: str):
        self.session = session
        self.key = key
        self.lock_id = lock_key_to_bigint(key)
        self.acquired: bool = False

    async def __aenter__(self) -> "PostgresAdvisoryLock":
        try:
            result = await self.session.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": self.lock_id}
            )
            got = result.scalar()
            self.acquired = bool(got)
        except Exception as exc:
            logger.warning(
                "PG advisory lock acquire failed, treating as NOT acquired: %s", exc
            )
            self.acquired = False
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if not self.acquired:
            return
        try:
            await self.session.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": self.lock_id}
            )
        except Exception as unlock_exc:
            # 不吞任务异常，仅记录 unlock 失败
            logger.warning("PG advisory lock release failed: %s", unlock_exc)
        finally:
            self.acquired = False


# ---------------------------------------------------------------------------
# RedisNXLock (best-effort 回退)
# ---------------------------------------------------------------------------
class RedisNXLock:
    """Redis SET NX EX best-effort 锁。

    语义：
      - 成功获取：`acquired=True`
      - 已被他人持有：`acquired=False`
      - Redis 不可用：`acquired=True`（退化为本实例执行，与原 D-018 行为保持一致）

    TTL 到期自动释放；`__aexit__` 里不强制 DEL，避免误删他人持有（无 owner token
    防护）。如需严格性请改用 `PostgresAdvisoryLock`。
    """

    def __init__(self, redis_client, key: str, ttl: int):
        self.redis = redis_client
        self.key = key
        self.ttl = ttl
        self.acquired: bool = False

    async def __aenter__(self) -> "RedisNXLock":
        if self.redis is None:
            # 无 Redis：退化为总是获取成功（best-effort）
            self.acquired = True
            return self
        try:
            got = await self.redis.set(self.key, "1", nx=True, ex=self.ttl)
            self.acquired = bool(got)
        except Exception as exc:
            logger.warning(
                "Redis lock error, fallback to local run: %s", exc
            )
            self.acquired = True  # 与历史行为一致
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # 不主动 DEL，依赖 TTL 释放（避免误删他人锁）
        self.acquired = False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def acquire_scheduler_lock(
    *,
    session: Optional[AsyncSession],
    redis_client,
    key: str,
    ttl: int,
) -> DistributedLock:
    """按环境自动选择锁实现。

    - Postgres: `PostgresAdvisoryLock`（生产主路径）
    - 否则: `RedisNXLock`（开发/测试/降级）
    """
    if session is not None and _session_dialect(session) == "postgresql":
        return PostgresAdvisoryLock(session, key)
    return RedisNXLock(redis_client, key, ttl)
