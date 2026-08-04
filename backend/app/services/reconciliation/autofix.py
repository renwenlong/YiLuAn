"""[ADR-0032 / TD-MONEY-01 M3 / D-044] 资金对账自动补偿。

Strategy matrix (per ADR §2.4 + D-044 Q3):

    MISSING_PAYMENT  -> auto_replay  (查询 provider，若已支付则补 ledger)
    ORPHAN_PAYMENT   -> escalate     (无对应业务订单，转人工)
    AMOUNT_MISMATCH  -> escalate     (金额不一致，必须人工核对)
    STATUS_MISMATCH  -> auto_replay  (相位错位，重放业务事件)

约束（ADR §2.4 / D-044 Q3）:
- 同一订单 24h 内最多 ``MAX_AUTO_RETRIES_PER_ORDER`` 次自动补偿；超过后强制 escalate。
- 每次尝试都写 ``reconciliation_actions`` 行（actor_id=NULL 表示系统）。
- ``provider="mock"`` 单独走 ``RECON_MOCK_AUTO_FIX_ENABLED`` 开关
  （D-044 Q5），失败不告警。

M3 出口：本模块暴露 :func:`autofix_diff` 和 :func:`autofix_run_diffs`
两个 entry point；前者用于单条 diff（admin 工单 / 增量队列），后者
用于批量补偿（cron T+1 跑完后自动调）。

**显式不做（M3）**：
- 真实 backfill（要 D-044 Q5 完整方案）
- 调用 provider "查询订单" API（M2 还未抽象出 ``provider.query_order``）
- 真正发起退款（admin H5 工单走 :mod:`app.services.payment_service`
  的 ``create_refund`` 入口，本模块只负责状态留痕）
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reconciliation import (
    ReconActionKind,
    ReconciliationAction,
    ReconciliationDiff,
    ReconDiffKind,
    ReconDiffStatus,
)

logger = logging.getLogger(__name__)


# 策略矩阵
_STRATEGY: dict[ReconDiffKind, ReconActionKind] = {
    ReconDiffKind.missing_payment: ReconActionKind.auto_replay,
    ReconDiffKind.status_mismatch: ReconActionKind.auto_replay,
    ReconDiffKind.amount_mismatch: ReconActionKind.escalate,
    ReconDiffKind.orphan_payment: ReconActionKind.escalate,
}

# 同一订单 24h 内最多 N 次自动补偿（D-044 Q3）
MAX_AUTO_RETRIES_PER_ORDER = 3
AUTO_RETRY_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class AutoFixResult:
    diff_id: uuid.UUID
    action_kind: ReconActionKind
    outcome: str  # "success" | "skipped" | "escalated" | "failed"
    error: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _count_recent_auto_attempts(
    session: AsyncSession,
    order_id: uuid.UUID,
    *,
    now: datetime,
) -> int:
    """Count auto_replay actions for ``order_id`` within the 24h window."""
    if order_id is None:
        return 0
    since = now - AUTO_RETRY_WINDOW
    stmt = (
        select(func.count(ReconciliationAction.id))
        .join(
            ReconciliationDiff,
            ReconciliationAction.diff_id == ReconciliationDiff.id,
        )
        .where(ReconciliationDiff.order_id == order_id)
        .where(ReconciliationAction.kind == ReconActionKind.auto_replay)
        .where(ReconciliationAction.created_at >= since)
    )
    result = await session.execute(stmt)
    return int(result.scalar() or 0)


def _record_action(
    session: AsyncSession,
    *,
    diff_id: uuid.UUID,
    kind: ReconActionKind,
    outcome: str,
    actor_id: uuid.UUID | None = None,
    payload: dict | None = None,
    error: str | None = None,
) -> ReconciliationAction:
    action = ReconciliationAction(
        diff_id=diff_id,
        kind=kind,
        actor_id=actor_id,
        payload=payload,
        outcome=outcome,
        error=error,
    )
    session.add(action)
    return action


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def autofix_diff(
    session: AsyncSession,
    diff: ReconciliationDiff,
    *,
    now: datetime | None = None,
) -> AutoFixResult:
    """Apply the M3 strategy matrix to a single diff row.

    Side effects (all on ``session`` — caller commits):
    - Writes one ``reconciliation_actions`` row.
    - Mutates ``diff.status`` / ``diff.auto_retry_count`` / ``diff.last_error``.
    """
    _now = now or datetime.now(timezone.utc)

    # Already terminal — no-op (idempotent for re-runs).
    if diff.status in (
        ReconDiffStatus.matched,
        ReconDiffStatus.compensated,
        ReconDiffStatus.closed,
    ):
        return AutoFixResult(
            diff_id=diff.id,
            action_kind=ReconActionKind.auto_replay,
            outcome="skipped",
            error=f"diff already terminal: {diff.status.value}",
        )

    strategy = _STRATEGY.get(diff.kind, ReconActionKind.escalate)

    # Per-order retry cap (only relevant for auto strategies).
    if strategy == ReconActionKind.auto_replay and diff.order_id is not None:
        recent = await _count_recent_auto_attempts(
            session, diff.order_id, now=_now
        )
        if recent >= MAX_AUTO_RETRIES_PER_ORDER:
            diff.status = ReconDiffStatus.mismatched
            diff.last_error = (
                f"auto_retry_cap_reached:{recent}/{MAX_AUTO_RETRIES_PER_ORDER}"
            )
            _record_action(
                session,
                diff_id=diff.id,
                kind=ReconActionKind.escalate,
                outcome="escalated",
                payload={"reason": "auto_retry_cap_reached", "count": recent},
            )
            await session.flush()
            return AutoFixResult(
                diff_id=diff.id,
                action_kind=ReconActionKind.escalate,
                outcome="escalated",
                error=f"retry cap {recent}/{MAX_AUTO_RETRIES_PER_ORDER}",
            )

    if strategy == ReconActionKind.escalate:
        diff.status = ReconDiffStatus.mismatched
        _record_action(
            session,
            diff_id=diff.id,
            kind=ReconActionKind.escalate,
            outcome="escalated",
            payload={
                "kind": diff.kind.value,
                "reason": "strategy=escalate",
            },
        )
        await session.flush()
        return AutoFixResult(
            diff_id=diff.id,
            action_kind=ReconActionKind.escalate,
            outcome="escalated",
        )

    # auto_replay path. M3 keeps it as a *bookkeeping* replay: we mark the
    # diff as ``compensated`` and bump the retry counter. Real provider
    # query/replay is M3+ (TODO: when ``provider.query_order`` exists,
    # call it here and only mark compensated on positive ack).
    diff.auto_retry_count = (diff.auto_retry_count or 0) + 1
    diff.status = ReconDiffStatus.compensated
    diff.last_error = None
    _record_action(
        session,
        diff_id=diff.id,
        kind=ReconActionKind.auto_replay,
        outcome="success",
        payload={
            "kind": diff.kind.value,
            "auto_retry_count": diff.auto_retry_count,
            # TODO(M3+): record provider.query_order response payload
            "todo": "provider_query_order_not_implemented",
        },
    )
    await session.flush()
    logger.info(
        "autofix_diff: diff=%s kind=%s -> compensated (retry=%d)",
        diff.id,
        diff.kind.value,
        diff.auto_retry_count,
    )
    return AutoFixResult(
        diff_id=diff.id,
        action_kind=ReconActionKind.auto_replay,
        outcome="success",
    )


async def autofix_run_diffs(
    session: AsyncSession,
    diff_ids: list[uuid.UUID],
    *,
    now: datetime | None = None,
) -> list[AutoFixResult]:
    """Bulk variant; iterates and calls :func:`autofix_diff` per row.

    Diffs are processed in the order given; failures are recorded but
    do not abort the loop.
    """
    # [S3-PERF-RECON-AUTOFIX-N1-BATCH AC#1] 批量预取消除 N+1:
    # 原实现在循环内逐行 ``await session.get(...)``, N 个 diff = N 次 DB
    # round-trip。改为循环前一次 ``SELECT ... WHERE id IN (...)`` 建
    # id->row map, 循环内改查 map。缺失 id 落 map 外, 仍走原 escalate/
    # skipped 分支 (AC#2); 循环顺序仍按入参 ``diff_ids`` (AC#3)。
    diff_map: dict[uuid.UUID, ReconciliationDiff] = {}
    if diff_ids:
        rows = await session.execute(
            select(ReconciliationDiff).where(
                ReconciliationDiff.id.in_(diff_ids)
            )
        )
        diff_map = {row.id: row for row in rows.scalars().all()}

    out: list[AutoFixResult] = []
    for did in diff_ids:
        diff = diff_map.get(did)
        if diff is None:
            out.append(
                AutoFixResult(
                    diff_id=did,
                    action_kind=ReconActionKind.escalate,
                    outcome="skipped",
                    error="diff not found",
                )
            )
            continue
        try:
            res = await autofix_diff(session, diff, now=now)
        except Exception as exc:  # pragma: no cover - defence
            logger.exception("autofix_diff failed for %s: %s", did, exc)
            diff.status = ReconDiffStatus.mismatched
            diff.last_error = str(exc)[:500]
            _record_action(
                session,
                diff_id=did,
                kind=ReconActionKind.auto_replay,
                outcome="failed",
                error=str(exc)[:500],
            )
            await session.flush()
            res = AutoFixResult(
                diff_id=did,
                action_kind=ReconActionKind.auto_replay,
                outcome="failed",
                error=str(exc)[:500],
            )
        out.append(res)
    return out
