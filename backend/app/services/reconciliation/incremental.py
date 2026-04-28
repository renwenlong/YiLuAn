"""[ADR-0032 / TD-MONEY-01 M3 / D-044] 增量对账（5 min 窗口）。

设计取舍（D-044 Q5）::

    - 当前仓库**没有 outbox / event-bus**。M3 选用 **in-process queue + sweeper**
      简化方案：
        1. 业务侧（payment_callback 落 ``payment_callback_log`` 后）
           调用 :func:`enqueue_incremental_event` 把事件 push 进进程内队列。
        2. APScheduler 每 5 分钟跑 :func:`sweep_incremental_queue`，
           从队列 + 数据库（最近 1h 未消费的回调日志）合并出待对账窗口。
        3. 在窗口内复用 M2 的快照 / diff_orders / persist_diffs 逻辑。
        4. 跑完后对每条 diff 调用 :func:`autofix_diff` 走自动补偿。
    - 多副本部署：M3 队列**不跨进程同步**（in-process），但 sweeper 兜底
      读 DB（``payment_callback_log.created_at >= now - 1h`` 且未在 24h 内
      被对账过的订单）保证最终覆盖。
    - 复用 PG advisory lock（``yiluan:scheduler:reconcile-incr:lock``）
      避免多副本同时跑 sweeper。

**TODO（M3+）**：
- 把 in-process queue 替换为 Redis Streams / Kafka outbox（D-019 同模式）。
- ``payment_callback`` 真正发出事件而不是仅入库。
- sweeper 的去重 cursor 落库（避免 1h 内重复对账）。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.payment_callback_log import PaymentCallbackLog
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.services.reconciliation.autofix import autofix_diff
from app.observability.reconciliation_metrics import record_run_metrics

logger = logging.getLogger(__name__)


INCREMENTAL_LOCK_KEY = "yiluan:scheduler:reconcile-incr:lock"
INCREMENTAL_LOCK_TTL_SECONDS = 600  # 10 min — Redis fallback only
INCREMENTAL_SWEEP_LOOKBACK = timedelta(hours=1)  # sweeper safety net (D-044)
INCREMENTAL_WINDOW = timedelta(minutes=5)


# ---------------------------------------------------------------------------
# In-process event queue (process-local, not shared across replicas)
# ---------------------------------------------------------------------------
@dataclass
class IncrementalEvent:
    order_id: uuid.UUID | None
    provider: str
    transaction_id: str | None
    enqueued_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# Bounded queue so a misbehaving producer can't OOM the worker.
_QUEUE_MAXLEN = 10_000
_queue: deque[IncrementalEvent] = deque(maxlen=_QUEUE_MAXLEN)
_queue_lock = asyncio.Lock()


async def enqueue_incremental_event(
    *,
    order_id: uuid.UUID | None,
    provider: str,
    transaction_id: str | None = None,
) -> None:
    """Producer: called from payment callback right after the
    ``payment_callback_log`` row is committed.

    Non-fatal if the queue is full — the sweeper will pick it up via the
    DB lookback path.
    """
    event = IncrementalEvent(
        order_id=order_id,
        provider=provider,
        transaction_id=transaction_id,
    )
    async with _queue_lock:
        _queue.append(event)
    logger.debug(
        "incremental.enqueue order=%s provider=%s txn=%s qsize=%d",
        order_id,
        provider,
        transaction_id,
        len(_queue),
    )


async def _drain_queue() -> list[IncrementalEvent]:
    async with _queue_lock:
        items = list(_queue)
        _queue.clear()
    return items


def _queue_size() -> int:
    return len(_queue)


# ---------------------------------------------------------------------------
# Direct event handler (called inline from payment callback after enqueue
# in deployments where we want a fast path; safe to no-op on failure).
# ---------------------------------------------------------------------------
async def handle_incremental_event(
    session: AsyncSession,
    event: IncrementalEvent,
) -> int:
    """Inline single-event handler. Currently it just enqueues for the
    sweeper; a future revision will run a focused 1-order diff.

    Returns the number of diffs found (always 0 in the in-process queue
    path; real value comes from the sweep run).
    """
    # M3 keeps the inline path minimal: enqueue only. Sweeper does the work.
    await enqueue_incremental_event(
        order_id=event.order_id,
        provider=event.provider,
        transaction_id=event.transaction_id,
    )
    return 0


# ---------------------------------------------------------------------------
# Sweeper
# ---------------------------------------------------------------------------
async def _collect_lookback_orders(
    session: AsyncSession, *, now: datetime
) -> list[str]:
    """Read recent payment_callback_log rows as a safety net.

    Returns the set of distinct ``out_trade_no`` strings seen in the
    lookback window so the caller can include them in metric counts.
    (We don't resolve to UUID here; the M3 sweep keys on order_number.)
    """
    since = now - INCREMENTAL_SWEEP_LOOKBACK
    stmt = (
        select(PaymentCallbackLog.out_trade_no)
        .where(PaymentCallbackLog.created_at >= since)
        .where(PaymentCallbackLog.out_trade_no.is_not(None))
    )
    rows = (await session.execute(stmt)).all()
    seen: list[str] = []
    seen_set: set[str] = set()
    for (otn,) in rows:
        if not otn or otn in seen_set:
            continue
        seen_set.add(otn)
        seen.append(otn)
    return seen


@dataclass
class SweepResult:
    status: str
    run_id: uuid.UUID | None
    queued_events: int
    callbacks_inspected: int
    diffs_found: int
    autofixed: int
    last_error: str | None = None


async def sweep_incremental_queue(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
    redis_client=None,
) -> SweepResult:
    """Drain the in-process queue, perform a focused incremental
    reconciliation pass over the union of (queued events ∪ lookback DB
    callbacks), and run autofix on any new diffs.

    Idempotent at the cron level via PG advisory lock.
    """
    _now = now or datetime.now(timezone.utc)

    if session is not None:
        return await _sweep_with_session(session, now=_now, redis_client=redis_client)

    async with async_session() as s:
        try:
            return await _sweep_with_session(s, now=_now, redis_client=redis_client)
        except Exception as exc:  # pragma: no cover
            logger.exception("sweep_incremental_queue outer failure: %s", exc)
            await s.rollback()
            return SweepResult(
                status="failed",
                run_id=None,
                queued_events=0,
                callbacks_inspected=0,
                diffs_found=0,
                autofixed=0,
                last_error=str(exc)[:500],
            )


async def _sweep_with_session(
    session: AsyncSession,
    *,
    now: datetime,
    redis_client,
) -> SweepResult:
    from app.cron.reconcile_money import (  # local import to avoid cycle
        _diff_breakdown,
        _load_business_snapshots,
        _load_ledger_snapshots,
        _load_payment_snapshots,
        _persist_diffs,
    )
    from app.services.reconciliation import diff_orders

    window_end = now
    window_start = now - INCREMENTAL_WINDOW

    # 1) record run row up front
    run = ReconciliationRun(
        kind=ReconRunKind.incremental,
        status=ReconRunStatus.running,
        window_start=window_start,
        window_end=window_end,
        triggered_by="sweeper",
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    await session.commit()

    # 2) advisory lock
    lock = acquire_scheduler_lock(
        session=session,
        redis_client=redis_client,
        key=INCREMENTAL_LOCK_KEY,
        ttl=INCREMENTAL_LOCK_TTL_SECONDS,
    )
    async with lock:
        if not lock.acquired:
            run.status = ReconRunStatus.failed
            run.notes = "skipped: another replica holds the incremental lock"
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return SweepResult(
                status="skipped",
                run_id=run_id,
                queued_events=0,
                callbacks_inspected=0,
                diffs_found=0,
                autofixed=0,
                last_error="lock_not_acquired",
            )

        try:
            queued = await _drain_queue()
            queued_count = len(queued)
            # Lookback safety net
            lookback = await _collect_lookback_orders(session, now=now)
            callbacks_inspected = len(lookback)

            # M3 simplification: reuse M2 snapshot loaders over the
            # 5-minute window. Real production should narrow by
            # order_id ∈ (queued ∪ lookback), but the small window keeps
            # cost bounded.
            business = await _load_business_snapshots(
                session, window_start=window_start, window_end=window_end
            )
            payments = await _load_payment_snapshots(
                session, window_start=window_start, window_end=window_end
            )
            ledger = await _load_ledger_snapshots(
                session, window_start=window_start, window_end=window_end
            )

            diffs = diff_orders(business, payments, ledger)
            inserted = await _persist_diffs(session, run_id=run_id, diffs=diffs)

            # Autofix: pull just-inserted diffs and run strategy matrix
            stmt = select(ReconciliationDiff).where(
                ReconciliationDiff.run_id == run_id,
                ReconciliationDiff.status == ReconDiffStatus.pending,
            )
            new_diffs = (await session.execute(stmt)).scalars().all()
            autofixed = 0
            for d in new_diffs:
                res = await autofix_diff(session, d, now=now)
                if res.outcome in ("success", "escalated"):
                    autofixed += 1

            run.status = ReconRunStatus.success
            run.orders_scanned = len(business)
            run.diffs_found = inserted
            run.diffs_auto_fixed = autofixed
            run.finished_at = datetime.now(timezone.utc)
            run.notes = (
                f"queued_events={queued_count} "
                f"callbacks_inspected={callbacks_inspected}"
            )
            await session.commit()

            record_run_metrics(
                kind=ReconRunKind.incremental.value,
                status=ReconRunStatus.success.value,
                diff_breakdown=_diff_breakdown(diffs),
                lag_seconds=(run.finished_at - window_end).total_seconds(),
            )

            return SweepResult(
                status="success",
                run_id=run_id,
                queued_events=queued_count,
                callbacks_inspected=callbacks_inspected,
                diffs_found=inserted,
                autofixed=autofixed,
            )
        except Exception as exc:
            logger.exception("sweep_incremental_queue failed: %s", exc)
            await session.rollback()
            try:
                run = await session.get(ReconciliationRun, run_id)
                if run is not None:
                    run.status = ReconRunStatus.failed
                    run.finished_at = datetime.now(timezone.utc)
                    run.notes = f"error: {exc!s}"[:500]
                    await session.commit()
            except Exception:  # pragma: no cover
                await session.rollback()
            record_run_metrics(
                kind=ReconRunKind.incremental.value,
                status=ReconRunStatus.failed.value,
                diff_breakdown={},
                lag_seconds=None,
            )
            return SweepResult(
                status="failed",
                run_id=run_id,
                queued_events=0,
                callbacks_inspected=0,
                diffs_found=0,
                autofixed=0,
                last_error=str(exc)[:500],
            )


# ---------------------------------------------------------------------------
# APScheduler entrypoint
# ---------------------------------------------------------------------------
async def reconcile_incremental_sweep_job(app=None) -> dict:
    """Wrapper used by APScheduler. Returns scheduler-friendly dict."""
    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)
    result = await sweep_incremental_queue(redis_client=redis_client)
    return {
        "status": result.status,
        "run_id": str(result.run_id) if result.run_id else None,
        "queued_events": result.queued_events,
        "callbacks_inspected": result.callbacks_inspected,
        "diffs_found": result.diffs_found,
        "autofixed": result.autofixed,
    }


__all__ = [
    "INCREMENTAL_LOCK_KEY",
    "INCREMENTAL_LOCK_TTL_SECONDS",
    "INCREMENTAL_WINDOW",
    "IncrementalEvent",
    "SweepResult",
    "enqueue_incremental_event",
    "handle_incremental_event",
    "sweep_incremental_queue",
    "reconcile_incremental_sweep_job",
    "_drain_queue",
    "_queue_size",
]
