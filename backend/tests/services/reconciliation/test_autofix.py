"""[ADR-0032 / TD-MONEY-01 M3 / D-044] autofix 单元测试。

覆盖：
- 策略矩阵（4 类 diff × 2 outcome = 8 case）
- 24h 重试上限（3 次后 escalate）
- 已 terminal 状态幂等 skip
- 批量 autofix_run_diffs（含 not-found / 异常路径）
- action 行写入正确（actor_id=NULL / kind / outcome / payload）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.reconciliation import (
    ReconActionKind,
    ReconciliationAction,
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.services.reconciliation.autofix import (
    MAX_AUTO_RETRIES_PER_ORDER,
    autofix_diff,
    autofix_run_diffs,
)
from tests.conftest import test_session_factory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _mk_run(session) -> ReconciliationRun:
    now = datetime.now(timezone.utc)
    run = ReconciliationRun(
        kind=ReconRunKind.full_t1,
        status=ReconRunStatus.running,
        window_start=now - timedelta(days=1),
        window_end=now,
        triggered_by="test",
    )
    session.add(run)
    await session.flush()
    return run


async def _mk_diff(
    session,
    run_id,
    *,
    kind: ReconDiffKind,
    status: ReconDiffStatus = ReconDiffStatus.pending,
    order_id=None,
    auto_retry_count: int = 0,
) -> ReconciliationDiff:
    diff = ReconciliationDiff(
        run_id=run_id,
        order_id=order_id or uuid.uuid4(),
        provider="wechat",
        provider_txn_id="txn_test",
        kind=kind,
        status=status,
        business_amount=Decimal("100.00"),
        payment_amount=Decimal("100.00"),
        ledger_amount=Decimal("100.00"),
        business_status="completed",
        payment_status="success",
        ledger_status="ok",
        auto_retry_count=auto_retry_count,
    )
    session.add(diff)
    await session.flush()
    return diff


# ---------------------------------------------------------------------------
# 策略矩阵
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "kind,expected_action,expected_status",
    [
        (ReconDiffKind.missing_payment, ReconActionKind.auto_replay, ReconDiffStatus.compensated),
        (ReconDiffKind.status_mismatch, ReconActionKind.auto_replay, ReconDiffStatus.compensated),
        (ReconDiffKind.amount_mismatch, ReconActionKind.escalate, ReconDiffStatus.mismatched),
        (ReconDiffKind.orphan_payment, ReconActionKind.escalate, ReconDiffStatus.mismatched),
    ],
)
async def test_autofix_strategy_matrix(kind, expected_action, expected_status):
    async with test_session_factory() as s:
        run = await _mk_run(s)
        diff = await _mk_diff(s, run.id, kind=kind)
        result = await autofix_diff(s, diff)
        await s.commit()

        assert result.action_kind == expected_action
        assert result.outcome in ("success", "escalated")
        await s.refresh(diff)
        assert diff.status == expected_status

        # action row written
        actions = (
            await s.execute(
                select(ReconciliationAction).where(
                    ReconciliationAction.diff_id == diff.id
                )
            )
        ).scalars().all()
        assert len(actions) == 1
        assert actions[0].kind == expected_action
        assert actions[0].actor_id is None  # system-driven


# ---------------------------------------------------------------------------
# 24h 重试上限
# ---------------------------------------------------------------------------
async def test_autofix_respects_24h_retry_cap():
    """同一订单 24h 内已尝试 3 次后强制 escalate。"""
    order_id = uuid.uuid4()
    async with test_session_factory() as s:
        run = await _mk_run(s)
        # 制造 3 次历史 auto_replay action
        for _ in range(MAX_AUTO_RETRIES_PER_ORDER):
            d = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment, order_id=order_id)
            d.status = ReconDiffStatus.compensated
            s.add(
                ReconciliationAction(
                    diff_id=d.id,
                    kind=ReconActionKind.auto_replay,
                    outcome="success",
                )
            )
        await s.flush()

        # 第 4 次应该 escalate
        new_diff = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment, order_id=order_id)
        result = await autofix_diff(s, new_diff)
        await s.commit()

        assert result.outcome == "escalated"
        assert result.action_kind == ReconActionKind.escalate
        await s.refresh(new_diff)
        assert new_diff.status == ReconDiffStatus.mismatched
        assert "auto_retry_cap_reached" in (new_diff.last_error or "")


async def test_autofix_old_attempts_outside_24h_dont_count():
    """24h 之外的历史尝试不计入 cap。"""
    order_id = uuid.uuid4()
    async with test_session_factory() as s:
        run = await _mk_run(s)
        # 25 小时前的 3 次尝试
        old = datetime.now(timezone.utc) - timedelta(hours=25)
        for _ in range(MAX_AUTO_RETRIES_PER_ORDER):
            d = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment, order_id=order_id)
            act = ReconciliationAction(
                diff_id=d.id,
                kind=ReconActionKind.auto_replay,
                outcome="success",
            )
            s.add(act)
            await s.flush()
            # backdate
            act.created_at = old
            await s.flush()

        new_diff = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment, order_id=order_id)
        result = await autofix_diff(s, new_diff)
        await s.commit()

        assert result.outcome == "success"
        assert result.action_kind == ReconActionKind.auto_replay


# ---------------------------------------------------------------------------
# 幂等 / 边界
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "terminal",
    [ReconDiffStatus.matched, ReconDiffStatus.compensated, ReconDiffStatus.closed],
)
async def test_autofix_skips_terminal_diff(terminal):
    async with test_session_factory() as s:
        run = await _mk_run(s)
        diff = await _mk_diff(
            s, run.id, kind=ReconDiffKind.missing_payment, status=terminal
        )
        result = await autofix_diff(s, diff)
        await s.commit()
        assert result.outcome == "skipped"

        actions = (
            await s.execute(
                select(ReconciliationAction).where(
                    ReconciliationAction.diff_id == diff.id
                )
            )
        ).scalars().all()
        assert actions == []


# ---------------------------------------------------------------------------
# 批量
# ---------------------------------------------------------------------------
async def test_autofix_run_diffs_handles_mixed_inputs():
    async with test_session_factory() as s:
        run = await _mk_run(s)
        d1 = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment)
        d2 = await _mk_diff(s, run.id, kind=ReconDiffKind.amount_mismatch)
        nonexistent = uuid.uuid4()
        results = await autofix_run_diffs(s, [d1.id, d2.id, nonexistent])
        await s.commit()

    assert len(results) == 3
    outcomes = [r.outcome for r in results]
    assert outcomes[0] == "success"
    assert outcomes[1] == "escalated"
    assert outcomes[2] == "skipped"
    assert results[2].error == "diff not found"


async def test_autofix_increments_retry_counter():
    async with test_session_factory() as s:
        run = await _mk_run(s)
        diff = await _mk_diff(
            s, run.id, kind=ReconDiffKind.missing_payment, auto_retry_count=1
        )
        result = await autofix_diff(s, diff)
        await s.commit()
        assert result.outcome == "success"
        await s.refresh(diff)
        assert diff.auto_retry_count == 2


# ---------------------------------------------------------------------------
# S3-PERF-RECON-AUTOFIX-N1-BATCH — 批量预取消除 N+1
# ---------------------------------------------------------------------------
async def _count_diff_selects(session, diff_ids):
    """跑 autofix_run_diffs 并统计针对 reconciliation_diffs 的 SELECT 次数."""
    from sqlalchemy import event

    seen: list[str] = []

    def _before_cursor_execute(conn, cursor, statement, *a, **k):
        sql = " ".join(statement.split())
        if sql.upper().startswith("SELECT") and "reconciliation_diffs" in sql:
            seen.append(sql)

    bind = session.get_bind()
    sync_engine = getattr(bind, "sync_engine", bind)
    event.listen(sync_engine, "before_cursor_execute", _before_cursor_execute)
    try:
        results = await autofix_run_diffs(session, diff_ids)
    finally:
        event.remove(sync_engine, "before_cursor_execute", _before_cursor_execute)
    return results, seen


async def test_autofix_run_diffs_batch_fetches_in_single_query():
    """AC#1: N 个 diff 的取行查询从 N 次降为 1 次批量 IN 查询."""
    async with test_session_factory() as s:
        run = await _mk_run(s)
        diffs = [
            await _mk_diff(s, run.id, kind=ReconDiffKind.amount_mismatch)
            for _ in range(5)
        ]
        diff_ids = [d.id for d in diffs]
        # 清 identity map，强制真实走 DB（否则 session.get 会命中缓存，
        # 掩盖 N+1 的真实 round-trip 数）
        s.expunge_all()

        results, selects = await _count_diff_selects(s, diff_ids)
        await s.commit()

    # 取行阶段只发 1 条 diff SELECT，且是 IN 批量查询
    fetch_selects = [q for q in selects if " IN (" in q.upper()]
    assert len(fetch_selects) == 1, (
        f"期望 1 条批量 IN 查询，实际 {len(fetch_selects)} 条: {fetch_selects}"
    )
    assert len(results) == 5
    assert all(r.outcome == "escalated" for r in results)


async def test_autofix_run_diffs_batch_preserves_order_and_missing():
    """AC#2/AC#3: 缺失 id 仍 escalate/skipped 不中断；结果顺序 == 入参顺序."""
    async with test_session_factory() as s:
        run = await _mk_run(s)
        d1 = await _mk_diff(s, run.id, kind=ReconDiffKind.amount_mismatch)
        d2 = await _mk_diff(s, run.id, kind=ReconDiffKind.missing_payment)
        miss_a = uuid.uuid4()
        miss_b = uuid.uuid4()
        # 缺失 id 穿插在中间和末尾，验证不中断且顺序对齐
        order = [miss_a, d1.id, miss_b, d2.id]
        results = await autofix_run_diffs(s, order)
        await s.commit()

    assert [r.diff_id for r in results] == order
    assert results[0].outcome == "skipped"
    assert results[0].action_kind == ReconActionKind.escalate
    assert results[0].error == "diff not found"
    assert results[1].outcome == "escalated"
    assert results[2].outcome == "skipped"
    assert results[2].error == "diff not found"
    assert results[3].outcome == "success"


async def test_autofix_run_diffs_empty_list_makes_no_query():
    """空入参不应发批量查询（避免 IN () 空集语法问题）."""
    async with test_session_factory() as s:
        results, selects = await _count_diff_selects(s, [])
    assert results == []
    assert selects == []
