"""后台定时任务调度器 (APScheduler)。

职责：
- 在 FastAPI lifespan 启动时初始化 AsyncIOScheduler，注册定时任务；
- 在 lifespan 关闭时优雅 shutdown。

当前注册的任务：
- `scan_expired_orders_job`：每分钟扫描一次过期订单并触发取消/退款（复用
  `OrderService.check_expired_orders` 实现）。详细选型与多副本权衡见
  `docs/DECISION_LOG.md` D-018。

多副本部署说明：
- 使用 Redis SET NX EX 作为 "best-effort" 分布式锁，保证同一时刻仅一个实例
  真正执行扫描任务，其他实例跳过本轮。锁 TTL 略小于任务调度间隔，避免单实例
  崩溃导致长时间无人扫描。
- Redis 不可用时退化为本实例单独执行（日志告警），不阻塞业务。
"""
from __future__ import annotations

import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.database import async_session

logger = logging.getLogger(__name__)

# 默认扫描间隔（秒）
EXPIRED_ORDER_SCAN_INTERVAL_SECONDS = 60

# 分布式锁 Key & TTL（秒）。TTL 略小于扫描间隔，避免锁释放漏洞导致长期挂起。
EXPIRED_ORDER_LOCK_KEY = "yiluan:scheduler:expired-orders:lock"
EXPIRED_ORDER_LOCK_TTL_SECONDS = 50


async def _try_acquire_lock(redis_client, key: str, ttl: int) -> bool:
    """尝试使用 Redis SET NX EX 获取分布式锁。

    失败（已被其他实例持有）或 redis 不可用时返回 False/True 的语义：
    - 成功获取：True
    - 已被他人持有：False
    - Redis 异常：返回 True（退化为本实例执行，避免任务完全不跑）。
    """
    if redis_client is None:
        return True
    try:
        # redis-py asyncio: set(nx=True, ex=ttl) 返回 True / None
        got = await redis_client.set(key, "1", nx=True, ex=ttl)
        return bool(got)
    except Exception as exc:  # pragma: no cover - 仅日志，退化执行
        logger.warning("scheduler lock redis error, fallback to local run: %s", exc)
        return True


async def scan_expired_orders_job(app=None) -> dict:
    """扫描过期订单并自动取消。

    - 自行创建 AsyncSession，避免依赖请求上下文。
    - 通过 Redis 分布式锁避免多副本重复执行。
    - 捕获并记录所有异常，保证调度器不会因一次失败而停摆。

    返回值主要便于单元测试断言：
        {"status": "ok"|"skipped"|"error", "cancelled": int}
    """
    # 延迟导入，避免循环依赖
    from app.services.order import OrderService

    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)

    acquired = await _try_acquire_lock(
        redis_client,
        EXPIRED_ORDER_LOCK_KEY,
        EXPIRED_ORDER_LOCK_TTL_SECONDS,
    )
    if not acquired:
        logger.debug("scan_expired_orders_job: another instance holds the lock, skip")
        return {"status": "skipped", "cancelled": 0}

    try:
        async with async_session() as session:
            try:
                service = OrderService(session)
                cancelled = await service.check_expired_orders()
                await session.commit()
                count = len(cancelled)
                if count:
                    logger.info("scan_expired_orders_job: cancelled %d expired orders", count)
                else:
                    logger.debug("scan_expired_orders_job: no expired orders")
                return {"status": "ok", "cancelled": count}
            except Exception:
                await session.rollback()
                raise
    except Exception as exc:
        logger.exception("scan_expired_orders_job failed: %s", exc)
        return {"status": "error", "cancelled": 0}


def create_scheduler(app) -> AsyncIOScheduler:
    """创建并配置调度器（不 start）。调用方负责 start()/shutdown()。"""
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
