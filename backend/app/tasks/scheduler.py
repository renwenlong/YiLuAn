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

from app.config import settings
from app.core.distributed_lock import (
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
    from app.cron.ai_summary_enqueue import process_pending_digests_job
    from app.cron.cleanup_emergency_pii import cleanup_emergency_pii
    from app.cron.contract_generate_pickup import contract_generate_pickup_job
    from app.cron.contract_worm_repair import contract_worm_repair_job
    from app.cron.reconcile_money import reconcile_money_job
    from app.cron.reconciliation_cleanup import reconciliation_cleanup_job
    from app.cron.share_token_scanner import scan_share_token_anomalies_job
    from app.services.reconciliation.incremental import reconcile_incremental_sweep_job
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
    # ADR-0029 / D-043: 每日 03:00 清理 emergency PII（contact 90d / event 180d）
    scheduler.add_job(
        cleanup_emergency_pii,
        trigger=CronTrigger(hour=3, minute=0),
        id="cleanup_emergency_pii",
        name="Cleanup emergency PII (ADR-0029 retention)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=600,
        replace_existing=True,
    )
    # ADR-0032 / D-044: T+1 资金全量对账——每日 02:00 GMT+8 (= 18:00 UTC 前一日)
    scheduler.add_job(
        reconcile_money_job,
        trigger=CronTrigger(hour=18, minute=0),  # UTC; 对应 GMT+8 02:00
        kwargs={"app": app},
        id="reconcile_money_t1",
        name="T+1 money reconciliation (ADR-0032)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=1800,
        replace_existing=True,
    )
    # ADR-0032 / D-044 / M3: 增量对账兜底 sweeper — 每 5 分钟扫一次队列
    scheduler.add_job(
        reconcile_incremental_sweep_job,
        trigger=IntervalTrigger(minutes=5),
        kwargs={"app": app},
        id="reconcile_money_incremental_sweep",
        name="Incremental reconciliation queue sweeper (ADR-0032)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
        replace_existing=True,
    )
    # ADR-0032 / D-044 Q4 / M3: 5 年保留期清理发现 cron — 每周一 03:00 GMT+8
    scheduler.add_job(
        reconciliation_cleanup_job,
        trigger=CronTrigger(day_of_week="mon", hour=19, minute=0),  # UTC ≈ Mon 03:00 GMT+8
        kwargs={"app": app},
        id="reconciliation_cleanup",
        name="Reconciliation 5y archive discovery (ADR-0032)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=3600,
        replace_existing=True,
    )
    # S2-DEV-006: 家属分享 token 异常扫描器 — 每 5 分钟，24h 滚动窗口
    # distinct openid > 5 → 自动 revoke。
    scheduler.add_job(
        scan_share_token_anomalies_job,
        trigger=IntervalTrigger(minutes=5),
        kwargs={"app": app},
        id="scan_share_token_anomalies",
        name="Family-share token anomaly scanner (S2-DEV-006)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=60,
        replace_existing=True,
    )
    # S2-DEV-006: AI 摘要 worker — 每分钟 drain pending AIDigest，
    # scheduler-lock 保证多副本只扣 1 次费 (ADR-0035 §3 P1-A)。
    scheduler.add_job(
        process_pending_digests_job,
        trigger=IntervalTrigger(minutes=1),
        kwargs={"app": app},
        id="process_pending_ai_digests",
        name="AI digest pending worker (S2-DEV-006)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
        replace_existing=True,
    )
    # S3-DEV-001-CONTRACT-PICKUP-CRON / ADR-0046 r5 §3: 拉起
    # pending_generation 合同行 → ContractService.generate_now 生成 PDF +
    # WORM-写 blob. 每 1min tick; 实际 batch 上限由
    # settings.contract_generate_pickup_batch_size 控制。
    scheduler.add_job(
        contract_generate_pickup_job,
        trigger=IntervalTrigger(minutes=1),
        kwargs={"app": app},
        id="contract_generate_pickup",
        name="Contract generation pickup (S3-DEV-001 PICKUP-CRON)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=30,
        replace_existing=True,
    )
    # S3-DEV-001-CONTRACT-WORM-COMPENSATION: WORM policy repair cron (默认每小时)
    scheduler.add_job(
        contract_worm_repair_job,
        trigger=IntervalTrigger(
            seconds=settings.contract_worm_repair_interval_seconds
        ),
        kwargs={"app": app},
        id="contract_worm_repair",
        name="Contract WORM policy repair (S3-DEV-001 WORM-COMPENSATION)",
        coalesce=True,
        max_instances=1,
        misfire_grace_time=120,
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
