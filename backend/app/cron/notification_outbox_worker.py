"""[S3-DEV-OUTBOX-2-WORKER] Notification outbox delivery worker (ADR-0058 §3.3 G2/G3).

设计：outbox 投递引擎 over the ``notification_outbox`` table
-----------------------------------------------------------------
DEV-1 的 ``enqueue_notification_outbox`` 在业务事务内写入 ``pending`` 行（不发
通知，保证业务主请求不被投递耗时拖住 + 原子回滚）。本 worker（DEV-2）周期性
drain ``pending`` / 到期 ``failed`` 行并执行**实际投递**，带退避重试 + 死信兜底。

复用模式（非复制代码，ADR-0058 决策 B）
----------------------------------------
照搬 ``ai_summary_enqueue.process_pending_digests_job`` 的骨架：
- 整段包 ``acquire_scheduler_lock``（ADR-0035 §3 红线，多副本只放行一个实例）
- batch 限单轮占锁时长
- 异常永不击穿调度器

在此骨架上**新增** ADR-0058 §3.3 的状态机：
- ``delivering`` 乐观锁认领（条件 UPDATE，防并发重复投递，AC#6）
- 投递成功 → ``delivered`` + ``delivered_at``（AC#3）
- 投递失败 → ``retry_count++`` 且指数退避算 ``next_retry_at`` → ``failed``（AC#3/#4）
- ``retry_count >= max_retries`` → ``dead`` + ``record_dead_letter``（AC#5）

边界（反案 #51）
----------------
本 worker **调用现有 ``NotificationService`` 的落库**执行投递，但**不修改**
业务侧通知接入点（把 ``notify_*`` 改 ``enqueue`` 属 DEV-3）。worker 从 outbox
行的 ``payload`` 反序列化投递参数，是 payload-driven 的通用 dispatch——这样
worker 自洽可测，DEV-3 只需让 enqueue 写对 payload schema。

退避公式（参数全走 config，ADR-0058 §0/§3.4 不写死）
----------------------------------------------------
``next_retry_at = now + min(base * factor^(retry_count-1), cap)``
- base = ``settings.notification_outbox_backoff_base_seconds``（默认 60s）
- factor = ``settings.notification_outbox_backoff_factor``（默认 2.0）
- cap = ``settings.notification_outbox_backoff_cap_seconds``（默认 3600s）
ADR §3.4 留白具体曲线 → 取业界标准，上线后按真实数据校准（AC#3 不断言死值）。
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.notification_outbox import (
    NotificationOutbox,
    NotificationOutboxStatus,
)
from app.services.dead_letter import record_dead_letter

logger = logging.getLogger("app.cron.notification_outbox_worker")

NOTIFICATION_OUTBOX_WORKER_LOCK_KEY = "yiluan:scheduler:notification-outbox-worker:lock"
# 锁 TTL 取略小于 tick 间隔，留余量；与 ai_digest worker 同思路（55s < 60s tick）。
NOTIFICATION_OUTBOX_WORKER_LOCK_TTL_SECONDS = 55


# DeliverFn: 给定 outbox 行，执行实际投递。失败抛异常（worker 捕获转重试/死信）。
# 默认实现见 ``_default_deliver``；单测可注入以模拟成功/失败（AC#3/#4 可验）。
DeliverFn = Callable[[AsyncSession, NotificationOutbox], Awaitable[None]]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _compute_next_retry_at(retry_count: int, *, now: Optional[datetime] = None) -> datetime:
    """指数退避: now + min(base * factor^(retry_count-1), cap).

    ``retry_count`` 是**本次失败后**的累计失败次数（>=1）。
    第 1 次失败 → base * factor^0 = base；第 2 次 → base * factor^1；以此类推，封顶 cap。
    参数全走 config（ADR-0058 §0 不写死）。
    """
    now = now or _now_utc()
    base = settings.notification_outbox_backoff_base_seconds
    factor = settings.notification_outbox_backoff_factor
    cap = settings.notification_outbox_backoff_cap_seconds
    exp = max(retry_count - 1, 0)
    delay = base * (factor**exp)
    delay = min(delay, cap)
    return now + timedelta(seconds=delay)


async def _default_deliver(session: AsyncSession, row: NotificationOutbox) -> None:
    """默认投递实现：从 payload 反序列化 → 调现有 NotificationService 落库。

    边界（反案 #51）：调用现有投递通道，不改业务接入点。payload schema 由
    DEV-3 enqueue 时写入；本 worker 是 payload-driven dispatch。

    payload 约定（DEV-3 对齐）::

        {
            "user_id": "<uuid str>",
            "type": "<NotificationType value>",
            "title": "...",
            "body": "...",
            "reference_id": "...",       # optional
            "target_type": "...",        # optional
            "target_id": "...",          # optional
        }

    失败（payload 缺字段 / 下游异常）→ 抛异常，由 worker 主循环转重试/死信。
    """
    import uuid as _uuid

    from app.models.notification import NotificationTargetType, NotificationType
    from app.services.notification import NotificationService

    payload = row.payload or {}
    user_id_raw = payload.get("user_id")
    if not user_id_raw:
        raise ValueError("outbox payload missing required field: user_id")

    notification_type = NotificationType(payload["type"])
    target_type_raw = payload.get("target_type")
    target_type = NotificationTargetType(target_type_raw) if target_type_raw is not None else None

    service = NotificationService(session)
    await service.create_notification(
        user_id=_uuid.UUID(str(user_id_raw)),
        type=notification_type,
        title=payload.get("title", ""),
        body=payload.get("body", ""),
        reference_id=payload.get("reference_id"),
        target_type=target_type,
        target_id=payload.get("target_id"),
    )


async def _claim_row(session: AsyncSession, row: NotificationOutbox) -> bool:
    """乐观锁认领：条件 UPDATE 把行从 (pending|failed) 翻成 delivering（AC#6）。

    用 ``WHERE id=:id AND status=:expected`` 的条件 UPDATE。并发副本即便同时
    捞到同一行，DB 行锁 + 条件保证只有一个 UPDATE 影响 1 行，其余影响 0 行
    （rowcount==0 → 认领失败，跳过）。scheduler-lock 是第一道防线，乐观锁是
    第二道（防同一实例内/锁退化为 best-effort 时的并发）。
    """
    expected = row.status
    result = await session.execute(
        update(NotificationOutbox)
        .where(
            NotificationOutbox.id == row.id,
            NotificationOutbox.status == expected,
        )
        .values(status=NotificationOutboxStatus.delivering)
    )
    claimed = (result.rowcount or 0) == 1
    if claimed:
        # 同步内存态，后续逐行处理读到的是 delivering。
        row.status = NotificationOutboxStatus.delivering
    return claimed


async def _process_one(
    session: AsyncSession,
    row: NotificationOutbox,
    deliver_fn: DeliverFn,
) -> str:
    """处理单行：认领 → 投递 → 成功 delivered / 失败 retry 或 dead。

    返回结果标签: "delivered" | "retry" | "dead" | "skipped"。
    每行独立 commit，避免一行失败回滚整批。
    """
    # 1) 乐观锁认领（AC#6）
    claimed = await _claim_row(session, row)
    if not claimed:
        # 其他实例已认领，跳过（不算错误）。
        await session.rollback()
        return "skipped"
    await session.commit()  # 固化 delivering，缩短认领窗口

    # 2) 实际投递
    try:
        await deliver_fn(session, row)
    except Exception as exc:  # 投递失败 → 重试或死信
        await session.rollback()  # 丢弃投递副作用（如半写的 notification）
        return await _handle_failure(session, row, exc)

    # 3) 投递成功 → delivered + delivered_at（AC#3）
    row.status = NotificationOutboxStatus.delivered
    row.delivered_at = _now_utc()
    row.last_error = None
    await session.commit()
    return "delivered"


async def _handle_failure(
    session: AsyncSession,
    row: NotificationOutbox,
    exc: Exception,
) -> str:
    """投递失败处理：retry_count++ → 退避重试 或 超阈值进死信（AC#3/#4/#5）。

    注意：进入此函数前已 rollback（清投递副作用），但 row 仍 detached/expired，
    需重新读最新值再改。这里直接基于内存 row 改并 merge，简单可靠。
    """
    new_retry_count = (row.retry_count or 0) + 1
    err_text = f"{type(exc).__name__}: {exc}"[:2000]

    if new_retry_count >= (row.max_retries or 0):
        # 超最大重试 → 死信（AC#5）。不静默丢：record_dead_letter + status=dead。
        row.status = NotificationOutboxStatus.dead
        row.retry_count = new_retry_count
        row.last_error = err_text
        await record_dead_letter(
            session,
            channel="notification",
            reason="delivery_exhausted",
            target_type="notification_outbox",
            target_id=row.id,
            payload={
                "outbox_id": str(row.id),
                "event_dedup_key": row.event_dedup_key,
                "retry_count": new_retry_count,
                "max_retries": row.max_retries,
                "last_error": err_text,
                "original_payload": row.payload,
            },
            flush=False,  # 由本函数统一 commit（cron 批量场景）
        )
        await session.commit()
        logger.warning(
            "notification_outbox row %s exhausted retries (%d), moved to dead-letter",
            row.id,
            new_retry_count,
        )
        return "dead"

    # 未超阈值 → 退避重试（AC#3/#4）
    row.status = NotificationOutboxStatus.failed
    row.retry_count = new_retry_count
    row.last_error = err_text
    row.next_retry_at = _compute_next_retry_at(new_retry_count)
    await session.commit()
    logger.info(
        "notification_outbox row %s delivery failed (retry %d/%d), next_retry_at=%s",
        row.id,
        new_retry_count,
        row.max_retries,
        row.next_retry_at,
    )
    return "retry"


async def _fetch_due_rows(
    session: AsyncSession, *, limit: int, now: Optional[datetime] = None
) -> list[NotificationOutbox]:
    """捞 status=pending OR (status=failed AND next_retry_at<=now) 的 N 行（AC#2）。

    走 index(status, next_retry_at)。FIFO by created_at 保证公平 + 至少一次。
    """
    now = now or _now_utc()
    stmt = (
        select(NotificationOutbox)
        .where(
            or_(
                NotificationOutbox.status == NotificationOutboxStatus.pending,
                (NotificationOutbox.status == NotificationOutboxStatus.failed)
                & (NotificationOutbox.next_retry_at <= now),
            )
        )
        .order_by(NotificationOutbox.created_at.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def process_notification_outbox_job(
    app=None,
    *,
    deliver_fn: Optional[DeliverFn] = None,
    batch_size: Optional[int] = None,
) -> dict:
    """Outbox 投递 worker entry（APScheduler kwargs={"app": app} 注入）。

    整段包 scheduler-lock（AC#1）。返回 dict 供测试断言::

        {"status": "ok"|"skipped"|"error",
         "delivered": int, "retried": int, "dead": int, "processed": int}

    异常永不击穿调度器（返回 error dict）。
    ``deliver_fn`` / ``batch_size`` 注入用于测试（AC#3/#4 模拟成败 + 控批量）。
    """
    deliver = deliver_fn or _default_deliver
    limit = batch_size if batch_size is not None else settings.notification_outbox_batch_size
    redis_client = getattr(app.state, "redis", None) if app is not None else None

    # enabled gate（与 prep_generate / contract_pickup 一致风格：内部检查）。
    # 注: 这是 worker tick 总开关（DEV-2）；业务侧 enqueue flag 属 DEV-3。
    # deliver_fn 注入时（测试）跳过 gate，便于单测无视 enabled 直接验状态机。
    if deliver_fn is None and not getattr(settings, "notification_outbox_worker_enabled", True):
        return {
            "status": "disabled",
            "delivered": 0,
            "retried": 0,
            "dead": 0,
            "processed": 0,
        }

    delivered = retried = dead = 0
    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=NOTIFICATION_OUTBOX_WORKER_LOCK_KEY,
                ttl=NOTIFICATION_OUTBOX_WORKER_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    # 其他副本持锁，本轮跳过（AC#1）。
                    return {
                        "status": "skipped",
                        "delivered": 0,
                        "retried": 0,
                        "dead": 0,
                        "processed": 0,
                    }

                rows = await _fetch_due_rows(session, limit=limit)
                for row in rows:
                    outcome = await _process_one(session, row, deliver)
                    if outcome == "delivered":
                        delivered += 1
                    elif outcome == "retry":
                        retried += 1
                    elif outcome == "dead":
                        dead += 1
                    # "skipped" 不计入 processed

        processed = delivered + retried + dead
        return {
            "status": "ok",
            "delivered": delivered,
            "retried": retried,
            "dead": dead,
            "processed": processed,
        }
    except Exception as exc:  # 永不击穿调度器
        logger.exception("notification_outbox_worker failed: %s", exc)
        return {
            "status": "error",
            "delivered": delivered,
            "retried": retried,
            "dead": dead,
            "processed": delivered + retried + dead,
        }
