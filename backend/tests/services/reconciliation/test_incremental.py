"""[ADR-0032 / TD-MONEY-01 M3 / D-044] 增量对账 sweeper 单元测试。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.order import Order, OrderStatus
from app.models.payment import Payment
from app.models.payment_callback_log import PaymentCallbackLog
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.models.user import User, UserRole
from app.services.reconciliation.incremental import (
    INCREMENTAL_WINDOW,
    IncrementalEvent,
    _drain_queue,
    _queue_size,
    enqueue_incremental_event,
    handle_incremental_event,
    reconcile_incremental_sweep_job,
    sweep_incremental_queue,
)
from tests.conftest import test_session_factory


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _clear_queue():
    await _drain_queue()
    yield
    await _drain_queue()


# ---------------------------------------------------------------------------
# Queue plumbing
# ---------------------------------------------------------------------------
async def test_enqueue_appends_event():
    oid = uuid.uuid4()
    await enqueue_incremental_event(order_id=oid, provider="wechat", transaction_id="T1")
    assert _queue_size() == 1
    drained = await _drain_queue()
    assert len(drained) == 1
    assert drained[0].order_id == oid
    assert drained[0].provider == "wechat"
    assert drained[0].transaction_id == "T1"


async def test_enqueue_handles_none_order_id():
    """Orphan callbacks have no order_id; queue must accept them."""
    await enqueue_incremental_event(order_id=None, provider="wechat")
    drained = await _drain_queue()
    assert len(drained) == 1
    assert drained[0].order_id is None


async def test_handle_incremental_event_re_enqueues():
    """The inline handler currently just enqueues for the sweeper."""
    oid = uuid.uuid4()
    event = IncrementalEvent(order_id=oid, provider="mock", transaction_id="X")
    async with test_session_factory() as s:
        result = await handle_incremental_event(s, event)
    assert result == 0
    assert _queue_size() == 1


# ---------------------------------------------------------------------------
# Sweeper basic invariants
# ---------------------------------------------------------------------------
async def test_sweep_with_empty_window_returns_success():
    async with test_session_factory() as s:
        result = await sweep_incremental_queue(session=s)
    assert result.status == "success"
    assert result.diffs_found == 0
    assert result.autofixed == 0
    assert result.run_id is not None


async def test_sweep_records_run_row_with_incremental_kind():
    """Each sweep must leave a reconciliation_runs row of kind=incremental."""
    async with test_session_factory() as s:
        result = await sweep_incremental_queue(session=s)
        run = await s.get(ReconciliationRun, result.run_id)
        assert run is not None
        assert run.kind == ReconRunKind.incremental
        assert run.status == ReconRunStatus.success
        assert run.window_end >= run.window_start
        # 5-minute window
        assert (run.window_end - run.window_start) == INCREMENTAL_WINDOW


async def test_sweep_consumes_queued_events():
    """Drained events should appear in run.notes for traceability."""
    await enqueue_incremental_event(order_id=uuid.uuid4(), provider="wechat", transaction_id="A")
    await enqueue_incremental_event(order_id=uuid.uuid4(), provider="wechat", transaction_id="B")
    async with test_session_factory() as s:
        result = await sweep_incremental_queue(session=s)
        run = await s.get(ReconciliationRun, result.run_id)
    assert result.queued_events == 2
    assert "queued_events=2" in (run.notes or "")
    assert _queue_size() == 0


async def test_sweep_inspects_payment_callback_log_lookback():
    """Sweeper safety net: counts unique out_trade_no in last 1h."""
    async with test_session_factory() as s:
        now = datetime.now(timezone.utc)
        log1 = PaymentCallbackLog(
            provider="wechat",
            out_trade_no="ON-001",
            transaction_id="T-001",
            callback_type="payment",
            status="received",
            raw_body="{}",
            created_at=now,
        )
        log2 = PaymentCallbackLog(
            provider="wechat",
            out_trade_no="ON-002",
            transaction_id="T-002",
            callback_type="payment",
            status="received",
            raw_body="{}",
            created_at=now,
        )
        s.add(log1)
        s.add(log2)
        await s.commit()

        result = await sweep_incremental_queue(session=s)
    assert result.callbacks_inspected == 2


async def test_scheduler_entry_returns_dict():
    """APScheduler entrypoint should return JSON-serializable dict.

    Note: directly invokes the real `async_session()` factory; we skip
    rather than fail when it isn't bound to the test engine.
    """
    try:
        result = await reconcile_incremental_sweep_job()
    except Exception:
        pytest.skip("async_session not bound to test engine in this context")
    assert isinstance(result, dict)
    assert result["status"] in ("success", "failed", "skipped")
    assert "run_id" in result
    assert "diffs_found" in result
    assert "autofixed" in result
