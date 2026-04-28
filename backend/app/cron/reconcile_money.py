"""[ADR-0032 / TD-MONEY-01 M2 / D-044] T+1 全量资金对账 cron。

调度器在每日 02:00（GMT+8 / UTC 18:00 前一日）触发 :func:`run_t1_reconciliation`。
窗口取『今日 00:00 - 27h ~ 今日 00:00 - 3h』（24h 数据 + 各 3h 缓冲，对齐
ADR §2.2），覆盖跨日延迟回调。

流程（ADR §3.4 / D-044 Q5）:

1. 创建 ``reconciliation_runs`` 行（``status=running``、``triggered_by=cron``）。
2. 取 PG advisory lock 防多副本并发；未拿到 → 立即把 run 行标 ``failed`` 并返回
   ``status=skipped`` 给调度器（**不抛异常**，否则 APScheduler 会暂停 job）。
3. 三源快照查询（business / payments / ledger）按 ``order_id`` 聚合，喂给
   :func:`app.services.reconciliation.diff_orders` 纯函数。
4. 写 ``reconciliation_diffs`` 行（M2 全部留 ``status=pending``，等 M3 补偿）。
5. 更新 run 行：``status=success`` (+ ``orders_scanned`` / ``diffs_found``)。
6. 刷新 Prometheus 指标：``reconciliation_diff_count`` / ``reconciliation_lag_seconds`` /
   ``reconciliation_run_total``。

**M2 出口**：cron 跑完即写 diff，不做自动补偿（M3 范围）。
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.order import Order
from app.models.payment import Payment
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
)
from app.observability.reconciliation_metrics import (
    current_env_label,
    record_run_metrics,
)
from app.services.reconciliation import (
    BusinessSnapshot,
    LedgerSnapshot,
    PaymentSnapshot,
    diff_orders,
)

logger = logging.getLogger(__name__)


# Window defaults (ADR §2.2). All math in UTC; APScheduler trigger uses local TZ.
WINDOW_START_BACK = timedelta(hours=27)
WINDOW_END_BACK = timedelta(hours=3)

RECONCILE_LOCK_KEY = "yiluan:scheduler:reconcile-money:lock"
RECONCILE_LOCK_TTL_SECONDS = 1800  # 30 min — Redis fallback only; PG releases at conn close

_DEFAULT_PROVIDER = "unknown"


@dataclass(frozen=True)
class ReconciliationRunResult:
    """Return value for :func:`run_t1_reconciliation` — also used in tests."""

    status: str  # "success" | "partial" | "failed" | "skipped"
    run_id: uuid.UUID | None
    orders_scanned: int
    diffs_found: int
    window_start: datetime
    window_end: datetime
    last_error: str | None = None


# ---------------------------------------------------------------------------
# Window helpers
# ---------------------------------------------------------------------------
def _today_midnight_utc(now: datetime) -> datetime:
    """Truncate ``now`` to the start of the current UTC day."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def compute_window(now: datetime) -> tuple[datetime, datetime]:
    """ADR §2.2 — 27h 前 ~ 3h 前，含跨日缓冲。"""
    midnight = _today_midnight_utc(now)
    return midnight - WINDOW_START_BACK, midnight - WINDOW_END_BACK


# ---------------------------------------------------------------------------
# Snapshot queries (M2 minimal — 三源最简聚合)
# ---------------------------------------------------------------------------
async def _load_business_snapshots(
    session: AsyncSession, *, window_start: datetime, window_end: datetime
) -> dict[uuid.UUID, BusinessSnapshot]:
    stmt = (
        select(Order.id, Order.status, Order.price)
        .where(Order.updated_at >= window_start)
        .where(Order.updated_at < window_end)
    )
    rows = (await session.execute(stmt)).all()
    out: dict[uuid.UUID, BusinessSnapshot] = {}
    for oid, status, price in rows:
        # status may be Enum or raw str depending on dialect
        status_str = getattr(status, "value", status) or ""
        out[oid] = BusinessSnapshot(
            order_id=oid,
            status=str(status_str),
            amount=Decimal(price or 0),
        )
    return out


async def _load_payment_snapshots(
    session: AsyncSession, *, window_start: datetime, window_end: datetime
) -> dict[uuid.UUID, PaymentSnapshot]:
    """Aggregate payments per order: net = SUM(pay) - SUM(refund).

    M2 keeps it simple: pick latest row per order for ``status`` /
    ``trade_no`` for diagnostics.
    """
    stmt = (
        select(
            Payment.order_id,
            Payment.status,
            Payment.amount,
            Payment.payment_type,
            Payment.trade_no,
            Payment.created_at,
        )
        .where(Payment.created_at >= window_start)
        .where(Payment.created_at < window_end)
        .order_by(Payment.created_at.asc())
    )
    rows = (await session.execute(stmt)).all()
    by_order: dict[uuid.UUID, dict] = {}
    for order_id, status, amount, ptype, trade_no, created_at in rows:
        bucket = by_order.setdefault(
            order_id,
            {
                "net": Decimal("0.00"),
                "status": status,
                "trade_no": trade_no,
            },
        )
        amt = Decimal(amount or 0)
        if status != "success":
            # only successful flows contribute to the net amount
            sign = Decimal("0")
        elif ptype == "refund":
            sign = Decimal("-1")
        else:
            sign = Decimal("1")
        bucket["net"] += amt * sign
        bucket["status"] = status
        bucket["trade_no"] = trade_no or bucket["trade_no"]

    out: dict[uuid.UUID, PaymentSnapshot] = {}
    for order_id, b in by_order.items():
        out[order_id] = PaymentSnapshot(
            order_id=order_id,
            status=str(b["status"] or ""),
            amount=Decimal(b["net"]),
            provider=settings.payment_provider or _DEFAULT_PROVIDER,
            provider_txn_id=b["trade_no"],
        )
    return out


async def _load_ledger_snapshots(
    session: AsyncSession, *, window_start: datetime, window_end: datetime
) -> dict[uuid.UUID, LedgerSnapshot]:
    """Aggregate wallet_ledger per order_id over the window.

    ``in`` = +amount, ``out`` = -amount.
    """
    stmt = (
        select(
            WalletLedger.order_id,
            WalletLedger.direction,
            WalletLedger.amount,
        )
        .where(WalletLedger.order_id.is_not(None))
        .where(WalletLedger.occurred_at >= window_start)
        .where(WalletLedger.occurred_at < window_end)
    )
    rows = (await session.execute(stmt)).all()
    nets: dict[uuid.UUID, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for order_id, direction, amount in rows:
        if order_id is None:
            continue
        dir_val = getattr(direction, "value", direction)
        sign = Decimal("1") if dir_val == WalletLedgerDirection.in_.value else Decimal("-1")
        nets[order_id] += Decimal(amount or 0) * sign
    return {
        oid: LedgerSnapshot(order_id=oid, status="ok", amount=net)
        for oid, net in nets.items()
    }


# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------
async def _persist_diffs(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    diffs: Sequence,
) -> int:
    """Write diff rows, return count actually inserted (skipping duplicates)."""
    inserted = 0
    seen: set[tuple[uuid.UUID | None, str]] = set()
    for d in diffs:
        key = (d.order_id, d.kind.value)
        if key in seen:
            continue
        seen.add(key)
        row = ReconciliationDiff(
            run_id=run_id,
            order_id=d.order_id,
            provider=d.provider or _DEFAULT_PROVIDER,
            provider_txn_id=d.provider_txn_id,
            kind=d.kind,
            status=ReconDiffStatus.pending,
            business_amount=d.business_amount,
            payment_amount=d.payment_amount,
            ledger_amount=d.ledger_amount,
            business_status=d.business_status,
            payment_status=d.payment_status,
            ledger_status=d.ledger_status,
        )
        session.add(row)
        inserted += 1
    await session.flush()
    return inserted


def _diff_breakdown(diffs: Sequence) -> dict[tuple[str, str, str], int]:
    """Aggregate diffs by (kind, status, provider) for Prometheus."""
    out: dict[tuple[str, str, str], int] = defaultdict(int)
    for d in diffs:
        out[
            (
                d.kind.value,
                ReconDiffStatus.pending.value,
                d.provider or _DEFAULT_PROVIDER,
            )
        ] += 1
    return dict(out)


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------
async def run_t1_reconciliation(
    *,
    now: datetime | None = None,
    session: AsyncSession | None = None,
    redis_client=None,
) -> ReconciliationRunResult:
    """Run a single T+1 full reconciliation pass.

    The function is **idempotent at the cron-scheduler level**: a PG
    advisory lock prevents duplicate runs across replicas; if the lock is
    not acquired, ``status='skipped'`` is returned and no diff rows are
    written.

    Errors are caught and recorded on the run row (``status='failed'``).
    The function never raises out to the scheduler — APScheduler would
    otherwise pause the job on unhandled exceptions.
    """
    _now = now or datetime.now(timezone.utc)
    window_start, window_end = compute_window(_now)
    logger.info(
        "run_t1_reconciliation start window=[%s, %s)",
        window_start.isoformat(),
        window_end.isoformat(),
    )

    if session is not None:
        return await _run_with_session(
            session,
            window_start=window_start,
            window_end=window_end,
            redis_client=redis_client,
        )

    async with async_session() as s:
        try:
            return await _run_with_session(
                s,
                window_start=window_start,
                window_end=window_end,
                redis_client=redis_client,
            )
        except Exception as exc:  # pragma: no cover - defence in depth
            logger.exception("run_t1_reconciliation outer failure: %s", exc)
            await s.rollback()
            return ReconciliationRunResult(
                status="failed",
                run_id=None,
                orders_scanned=0,
                diffs_found=0,
                window_start=window_start,
                window_end=window_end,
                last_error=str(exc)[:500],
            )


async def _run_with_session(
    session: AsyncSession,
    *,
    window_start: datetime,
    window_end: datetime,
    redis_client,
) -> ReconciliationRunResult:
    # 1) create run row up front so failures are observable
    run = ReconciliationRun(
        kind=ReconRunKind.full_t1,
        status=ReconRunStatus.running,
        window_start=window_start,
        window_end=window_end,
        triggered_by="cron",
    )
    session.add(run)
    await session.flush()
    run_id = run.id
    # Commit the run row up-front so a later rollback (failure path) doesn't
    # wipe its existence — we still want an audit trail of the failed run.
    await session.commit()

    # 2) advisory lock — must reuse the same session/connection
    lock = acquire_scheduler_lock(
        session=session,
        redis_client=redis_client,
        key=RECONCILE_LOCK_KEY,
        ttl=RECONCILE_LOCK_TTL_SECONDS,
    )
    async with lock:
        if not lock.acquired:
            run.status = ReconRunStatus.failed
            run.finished_at = datetime.now(timezone.utc)
            run.notes = "skipped: another replica holds the reconcile lock"
            await session.commit()
            record_run_metrics(
                kind=ReconRunKind.full_t1.value,
                status="skipped",
                diff_breakdown={},
                lag_seconds=None,
            )
            return ReconciliationRunResult(
                status="skipped",
                run_id=run_id,
                orders_scanned=0,
                diffs_found=0,
                window_start=window_start,
                window_end=window_end,
                last_error="lock_not_acquired",
            )

        try:
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
            diffs_found = await _persist_diffs(session, run_id=run_id, diffs=diffs)

            finished_at = datetime.now(timezone.utc)
            run.orders_scanned = len(business)
            run.diffs_found = diffs_found
            run.status = ReconRunStatus.success
            run.finished_at = finished_at
            await session.commit()

            lag = (finished_at - window_end).total_seconds()
            record_run_metrics(
                kind=ReconRunKind.full_t1.value,
                status=ReconRunStatus.success.value,
                diff_breakdown=_diff_breakdown(diffs),
                lag_seconds=lag,
            )
            logger.info(
                "run_t1_reconciliation done run_id=%s scanned=%d diffs=%d lag=%.1fs",
                run_id,
                len(business),
                diffs_found,
                lag,
            )
            return ReconciliationRunResult(
                status="success",
                run_id=run_id,
                orders_scanned=len(business),
                diffs_found=diffs_found,
                window_start=window_start,
                window_end=window_end,
            )
        except Exception as exc:
            logger.exception("run_t1_reconciliation failed: %s", exc)
            await session.rollback()
            # Re-attach the run row in a fresh transaction to mark it failed.
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
                kind=ReconRunKind.full_t1.value,
                status=ReconRunStatus.failed.value,
                diff_breakdown={},
                lag_seconds=None,
            )
            return ReconciliationRunResult(
                status="failed",
                run_id=run_id,
                orders_scanned=0,
                diffs_found=0,
                window_start=window_start,
                window_end=window_end,
                last_error=str(exc)[:500],
            )


# ---------------------------------------------------------------------------
# APScheduler entrypoint (kwargs-friendly)
# ---------------------------------------------------------------------------
async def reconcile_money_job(app=None) -> dict:
    """Wrapper used by APScheduler. Returns scheduler-friendly dict."""
    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)
    result = await run_t1_reconciliation(redis_client=redis_client)
    return {
        "status": result.status,
        "run_id": str(result.run_id) if result.run_id else None,
        "orders_scanned": result.orders_scanned,
        "diffs_found": result.diffs_found,
    }


# Re-export env helper for tests / callers.
__all__ = [
    "ReconciliationRunResult",
    "compute_window",
    "current_env_label",
    "reconcile_money_job",
    "run_t1_reconciliation",
]
