"""后台定时任务调度器 (APScheduler)。

职责：
- 在 FastAPI lifespan 启动时初始化 AsyncIOScheduler，注册定时任务；
- 在 lifespan 关闭时优雅 shutdown。

当前注册的任务：
- `scan_expired_orders_job`：每分钟扫描一次过期订单并触发取消/退款
  （复用 `OrderService.check_expired_orders`）。
  详细选型见 `docs/DECISION_LOG.md` D-018（含 2026-04-17 升级更新）。

## 分布式锁（D-018 生产级升级）

本调度器使用 `app.core.distributed_lock` 提供的统一抽象：
- **PostgreSQL 部署**：`PostgresAdvisoryLock`（`pg_try_advisory_lock`），强一致、
  连接断开自动释放，**彻底解决多副本重复扫描/时钟漂移问题**。
- **非 PG / 测试**：`RedisNXLock`（SET NX EX）best-effort，与历史行为保持一致。
- **两者皆不可用**：退化为本实例执行，保证任务不会完全停摆。

关键实现点：持锁与业务工作在同一个 AsyncSession 内完成 —— 对 PG advisory lock
来说必须是同一连接，否则 unlock 无效。
"""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.distributed_lock import (
    PostgresAdvisoryLock,
    RedisNXLock,
    acquire_scheduler_lock,
)
from app.database import async_session

logger = logging.getLogger(__name__)

# 默认扫描间隔（秒）
EXPIRED_ORDER_SCAN_INTERVAL_SECONDS = 60

# 分布式锁 Key & TTL（秒）。TTL 仅对 Redis 回退路径生效；PG advisory 随连接释放。
EXPIRED_ORDER_LOCK_KEY = "yiluan:scheduler:expired-orders:lock"
EXPIRED_ORDER_LOCK_TTL_SECONDS = 50


async def scan_expired_orders_job(app=None) -> dict:
    """扫描过期订单并自动取消。

    - 自行创建 AsyncSession，避免依赖请求上下文。
    - 通过分布式锁避免多副本重复执行：
        * PostgreSQL → `pg_try_advisory_lock`（强一致）
        * 其他 / 测试 → Redis SET NX EX（best-effort）
    - 捕获并记录所有异常，保证调度器不会因一次失败而停摆。

    返回值主要便于单元测试断言：
        {"status": "ok"|"skipped"|"error", "cancelled": int}
    """
    # 延迟导入，避免循环依赖
    from app.services.order import OrderService

    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)

    try:
        # 关键：锁与业务工作必须在同一个 AsyncSession 内，确保 PG advisory lock
        # 使用的连接与业务执行的连接一致。
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=EXPIRED_ORDER_LOCK_KEY,
                ttl=EXPIRED_ORDER_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "scan_expired_orders_job: another instance holds the lock (%s), skip",
                        type(lock).__name__,
                    )
                    return {"status": "skipped", "cancelled": 0}

                try:
                    service = OrderService(session)
                    cancelled = await service.check_expired_orders()
                    await session.commit()
                    count = len(cancelled)
                    if count:
                        logger.info(
                            "scan_expired_orders_job: cancelled %d expired orders (lock=%s)",
                            count,
                            type(lock).__name__,
                        )
                    else:
                        logger.debug("scan_expired_orders_job: no expired orders")
                    return {"status": "ok", "cancelled": count}
                except Exception:
                    await session.rollback()
                    raise
    except Exception as exc:
        logger.exception("scan_expired_orders_job failed: %s", exc)
        return {"status": "error", "cancelled": 0}


# ---------------------------------------------------------------------------
# 向后兼容：保留旧 helper（已被 `acquire_scheduler_lock` 取代），供旧测试使用。
# 不再在 scan_expired_orders_job 内调用。
# ---------------------------------------------------------------------------
async def _try_acquire_lock(redis_client, key: str, ttl: int) -> bool:
    """[DEPRECATED] 旧版 Redis NX 锁 helper，仅为向后兼容保留。

    新代码请使用 `app.core.distributed_lock.acquire_scheduler_lock`。
    """
    if redis_client is None:
        return True
    try:
        got = await redis_client.set(key, "1", nx=True, ex=ttl)
        return bool(got)
    except Exception as exc:  # pragma: no cover - 仅日志，退化执行
        logger.warning("scheduler lock redis error, fallback to local run: %s", exc)
        return True


def create_scheduler(app) -> AsyncIOScheduler:
    """创建并配置调度器（不 start）。调用方负责 start()/shutdown()。"""
    from app.tasks.log_retention import (
        cleanup_payment_callback_log,
        cleanup_sms_send_log,
    )

    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        scan_expired_orders_job,
        trigger=IntervalTrigger(seconds=EXPIRED_ORDER_SCAN_INTERVAL_SECONDS),
        kwargs={"app": app},
        id="scan_expired_orders",
        name="Scan expired orders and auto-cancel",
        coalesce=True,          # 多次错过的触发合并成一次
        max_instances=1,        # 同进程内防并发
        misfire_grace_time=30,  # 容忍 30 秒延迟
        replace_existing=True,
    )
    # D-027: 日志保留清理 — 每天凌晨 3:00 清理 payment_callback_log
    scheduler.add_job(
        cleanup_payment_callback_log,
        trigger=CronTrigger(hour=3, minute=0),
        kwargs={"app": app},
        id="cleanup_payment_callback_log",
        name="Cleanup expired payment callback logs",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
        replace_existing=True,
    )
    # D-027: 日志保留清理 — 每天凌晨 3:30 清理 sms_send_log
    scheduler.add_job(
        cleanup_sms_send_log,
        trigger=CronTrigger(hour=3, minute=30),
        kwargs={"app": app},
        id="cleanup_sms_send_log",
        name="Cleanup expired SMS send logs",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
        replace_existing=True,
    )
    return scheduler


_scheduler: Optional[AsyncIOScheduler] = None


def start_scheduler(app) -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        return _scheduler
    _scheduler = create_scheduler(app)
    _scheduler.start()
    logger.info(
        "Scheduler started, scan interval=%ds",
        EXPIRED_ORDER_SCAN_INTERVAL_SECONDS,
    )
    return _scheduler


async def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is None:
        return
    try:
        _scheduler.shutdown(wait=False)
    except Exception as exc:  # pragma: no cover
        logger.warning("Scheduler shutdown error: %s", exc)
    finally:
        _scheduler = None
        logger.info("Scheduler shut down")
