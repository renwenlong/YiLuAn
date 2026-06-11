"""[S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD / ADR-0048 §6 §8 P4]

Preparation package generate cron worker
-----------------------------------------

Mirrors ``contract_generate_pickup`` 双层防御 (idempotent enqueue + scheduler lock):

1. **Enqueue idempotency**: ``preparation_packages.order_id`` UNIQUE — 订单创建
   侧 insert pending row, 重复创建被 UQ 拦.
2. **Per-order Redis lock**: 每行处理时拿 ``lock:prep.generate:order:{order_id}``
   (TTL 120s = 2x cron 间隔), 避免同 order 同时被两个 replica 处理.
3. **Scheduler lock (外层)**: 批处理外层 scheduler-lock 防多 replica 同 tick
   全跑(节约 DB load).

Cron 调度: 每 1 分钟一次(魈 Q3 拍板). Batch size 受 ``settings.prep_generate_batch_size``
控制(默认 10).

调用链:

```
prep_generate_job (本模块)
  └─ acquire scheduler-lock (outer)
  └─ select pending PreparationPackage 行 (LIMIT batch_size, ORDER BY created_at ASC)
  └─ for each row:
       └─ acquire per-order Redis lock TTL 120s
       └─ PrepGenerateService.generate_for_order(order_id)
       └─ release per-order Redis lock
```

settings flag: ``settings.prep_generate_enabled = True`` (默认开).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.core.distributed_lock import RedisNXLock, acquire_scheduler_lock
from app.database import async_session
from app.models.preparation_package import PreparationPackage, PrepStatus
from app.services.prep_generate_service import generate_for_order

logger = logging.getLogger("app.cron.prep_generate")


PREP_GENERATE_LOCK_KEY = "yiluan:scheduler:prep-generate:lock"
PREP_GENERATE_LOCK_TTL_SECONDS = 55  # 一 tick 内做完, 60s cron 留 5s 余量

# per-order lock: 2x cron 间隔 = 120s, 防同 order 双跑
def _per_order_lock_key(order_id) -> str:
    return f"lock:prep.generate:order:{order_id}"

PER_ORDER_LOCK_TTL_SECONDS = 120


async def prep_generate_job(app: Any = None) -> dict[str, Any]:
    """Scheduler-locked + per-order locked worker: 推 pending → terminal.

    Returns ``{"status": "ok|skipped|disabled|error", "processed": int,
    "fallback": int, "failed": int}`` for test assertions and operator visibility.

    Behavior:
      * settings.prep_generate_enabled == False → ``{"status": "disabled", ...}``
      * 拿 scheduler 锁失败 → ``{"status": "skipped", ...}``
      * Batch 处理: 每行单独 per-order lock(失败 = 别 replica 在处理 → skip 该行)
      * Single row failures(generate_for_order 抛) 不阻批 — log + counter.
    """
    if not getattr(settings, "prep_generate_enabled", True):
        return {"status": "disabled", "processed": 0, "fallback": 0, "failed": 0}

    redis_client = getattr(app.state, "redis", None) if app is not None else None
    processed = 0
    fallback = 0
    failed = 0
    skipped_locked = 0
    batch_size = getattr(settings, "prep_generate_batch_size", 10)

    try:
        async with async_session() as session:
            outer_lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=PREP_GENERATE_LOCK_KEY,
                ttl=PREP_GENERATE_LOCK_TTL_SECONDS,
            )
            async with outer_lock:
                if not outer_lock.acquired:
                    logger.debug(
                        "prep_generate: another replica holds the scheduler lock, skip"
                    )
                    return {
                        "status": "skipped",
                        "processed": 0, "fallback": 0, "failed": 0,
                    }

                stmt = (
                    select(PreparationPackage)
                    .where(PreparationPackage.status == PrepStatus.pending)
                    .order_by(PreparationPackage.created_at.asc())
                    .limit(batch_size)
                )
                rows = (await session.execute(stmt)).scalars().all()
                if not rows:
                    return {
                        "status": "ok",
                        "processed": 0, "fallback": 0, "failed": 0,
                    }

                # S3-DEV-003 c5: collect order_ids that flipped to
                # active / active_fallback_template so we can trigger
                # precheck recompute + WS broadcast after the loop.
                # Hook is best-effort; failures cannot poison the
                # outer cron transaction.
                hook_order_ids: list = []

                for package in rows:
                    order_id = package.order_id

                    # per-order Redis lock
                    if redis_client is not None:
                        per_lock = RedisNXLock(
                            redis_client,
                            key=_per_order_lock_key(order_id),
                            ttl=PER_ORDER_LOCK_TTL_SECONDS,
                        )
                        async with per_lock:
                            if not per_lock.acquired:
                                skipped_locked += 1
                                logger.info(
                                    "prep.generate per-order lock not acquired"
                                    " order_id=%s — another worker processing",
                                    order_id,
                                )
                                continue
                            await _process_one(
                                redis_client, order_id, counters={
                                    "processed": processed,
                                    "fallback": fallback,
                                    "failed": failed,
                                },
                            )
                    else:
                        # redis 不可用(纯 sqlite dev / 测试) — 跳 per-order lock
                        await _process_one(
                            redis_client, order_id, counters={
                                "processed": processed,
                                "fallback": fallback,
                                "failed": failed,
                            },
                        )

                    # 重读结果 (process 自己开新 session 改 status)
                    async with async_session() as check_session:
                        check_stmt = select(PreparationPackage).where(
                            PreparationPackage.order_id == order_id,
                        )
                        result_pkg = (
                            await check_session.execute(check_stmt)
                        ).scalar_one_or_none()
                    if result_pkg is None:
                        continue
                    if result_pkg.status == PrepStatus.active:
                        processed += 1
                        hook_order_ids.append(order_id)
                    elif result_pkg.status == PrepStatus.active_fallback_template:
                        fallback += 1
                        hook_order_ids.append(order_id)
                    elif result_pkg.status == PrepStatus.generation_failed:
                        failed += 1

                # S3-DEV-003 c5: precheck recompute hook fan-out.
                # _process_one already committed its own session per
                # row, so we can fan-out immediately. Hook helper
                # swallows per-order errors.
                if hook_order_ids and app is not None:
                    from app.services.precheck_recompute_hook import (
                        CARD_PREPARATION,
                        trigger_precheck_recompute_for_orders,
                    )

                    async with async_session() as hook_session:
                        await trigger_precheck_recompute_for_orders(
                            app=app,
                            session=hook_session,
                            redis=redis_client,
                            order_ids=hook_order_ids,
                            card=CARD_PREPARATION,
                        )

    except Exception as exc:  # pragma: no cover - safety net
        logger.error("prep.generate.batch_error", exc_info=exc)
        return {
            "status": "error",
            "processed": processed,
            "fallback": fallback,
            "failed": failed,
        }

    return {
        "status": "ok",
        "processed": processed,
        "fallback": fallback,
        "failed": failed,
        "skipped_locked": skipped_locked,
    }


async def _process_one(redis_client, order_id, *, counters: dict) -> None:
    """单 order 处理: 开新 session(隔离每行错), 调 generate_for_order."""
    try:
        async with async_session() as session:
            await generate_for_order(
                session, redis_client, order_id=order_id,
            )
    except Exception as exc:  # pragma: no cover - safety net
        logger.error(
            "prep.generate.row_unexpected_error order_id=%s",
            order_id, exc_info=exc,
        )


__all__ = [
    "PREP_GENERATE_LOCK_KEY",
    "PER_ORDER_LOCK_TTL_SECONDS",
    "prep_generate_job",
]
