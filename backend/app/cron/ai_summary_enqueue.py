"""[S2-DEV-006] AI summary enqueue + scheduler-locked worker.

设计：outbox-lite over the ``AIDigest`` table
------------------------------------------------
``order.completed`` 不直接调 DeepSeek（那会让订单完成请求被 LLM 延迟拖住，
且多副本/重试会重复扣费）。改为：

1. **enqueue**: ``enqueue_ai_digest(order_id)`` upsert 一行
   ``AIDigest(status=PENDING)``。``order_id`` 唯一约束 → 天然幂等，
   ``complete_order`` 被重复调用也只有一行 pending（acceptance #10 第一道防线）。

2. **worker**: ``process_pending_digests_job`` 每分钟跑一次，**整段包在
   ``acquire_scheduler_lock`` 里**——多副本下同一轮只有一个实例真正处理
   pending 行 → 每个 order 只扣一次费（acceptance #10 第二道防线，对齐
   ADR-0035 §3 P1-A scheduler-lock red line）。

两道防线叠加：幂等 enqueue 防「同 order 多行」，scheduler-lock 防「多副本
同时处理同一行」。即使两个副本同一毫秒拿到同一 pending 行，advisory lock
只放行一个，另一个 skip。
"""
from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.ai_digest import AIDigest, AIDigestStatus
from app.services.ai_summary.digester import generate_digest

logger = logging.getLogger("app.cron.ai_summary_enqueue")

AI_DIGEST_WORKER_LOCK_KEY = "yiluan:scheduler:ai-digest-worker:lock"
AI_DIGEST_WORKER_LOCK_TTL_SECONDS = 55
# 单轮最多处理多少 pending，避免一次锁占用过久。
AI_DIGEST_BATCH_SIZE = 20


async def enqueue_ai_digest(session: AsyncSession, order_id: UUID) -> bool:
    """Idempotently mark an order as needing an AI digest.

    Returns True if a new pending row was created, False if a digest row
    already exists (any status — we don't re-enqueue an order that already
    has an ok/degraded/failed digest; re-generation is a manual op).
    """
    existing = (
        await session.execute(
            select(AIDigest).where(AIDigest.order_id == order_id)
        )
    ).scalar_one_or_none()
    if existing is not None:
        return False
    session.add(AIDigest(order_id=order_id, status=AIDigestStatus.PENDING))
    await session.flush()
    return True


def _build_prompt(order) -> str:
    """Minimal timeline prompt. S2-DEV-006 wires the order event timeline;
    the digester does the budget/post-check heavy lifting regardless of
    prompt shape."""
    parts = [
        f"订单号：{getattr(order, 'order_number', '')}",
        f"服务类型：{getattr(order, 'service_type', '')}",
        f"预约日期：{getattr(order, 'appointment_date', '')}",
    ]
    return "本次陪诊就诊过程时间线：\n" + "\n".join(p for p in parts if p)


async def process_pending_digests_job(app=None) -> dict:
    """Scheduler-locked worker: drain pending AIDigest rows.

    Returns {"status": ..., "processed": int} for test assertions.
    """
    redis_client = getattr(app.state, "redis", None) if app is not None else None
    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=AI_DIGEST_WORKER_LOCK_KEY,
                ttl=AI_DIGEST_WORKER_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "ai_digest_worker: another instance holds the lock, skip"
                    )
                    return {"status": "skipped", "processed": 0}

                pending = (
                    await session.execute(
                        select(AIDigest)
                        .where(AIDigest.status == AIDigestStatus.PENDING)
                        .order_by(AIDigest.created_at.asc())
                        .limit(AI_DIGEST_BATCH_SIZE)
                    )
                ).scalars().all()

                if not pending:
                    return {"status": "ok", "processed": 0}

                from app.repositories.order import OrderRepository

                order_repo = OrderRepository(session)
                redis = getattr(app.state, "redis", None) if app else None
                processed = 0
                for digest in pending:
                    order = await order_repo.get_by_id(digest.order_id)
                    if order is None:
                        digest.status = AIDigestStatus.FAILED
                        digest.degraded_reason = "order_missing"
                        await session.commit()
                        continue
                    # digester owns its own commit + metrics + dead_letter.
                    await generate_digest(
                        session=session,
                        redis=redis,
                        order_id=digest.order_id,
                        prompt=_build_prompt(order),
                    )
                    processed += 1
                return {"status": "ok", "processed": processed}
    except Exception as exc:
        logger.exception("ai_digest_worker failed: %s", exc)
        return {"status": "error", "processed": 0}


__all__ = [
    "AI_DIGEST_WORKER_LOCK_KEY",
    "enqueue_ai_digest",
    "process_pending_digests_job",
]
