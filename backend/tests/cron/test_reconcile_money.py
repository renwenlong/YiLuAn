"""[ADR-0032 / TD-MONEY-01 M2] T+1 reconciliation cron tests.

The tests share a single SQLite database fixture with the rest of the
suite (``setup_database`` autouse). PG advisory lock is unavailable on
SQLite, so the cron transparently falls back to the in-memory
"always-acquired" lock — concurrency behaviour is exercised by patching
``acquire_scheduler_lock`` directly.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.cron import reconcile_money as cron_module
from app.cron.reconcile_money import (
    ReconciliationRunResult,
    compute_window,
    run_t1_reconciliation,
)
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconRunStatus,
)
from app.models.wallet_ledger import (
    WalletLedger,
    WalletLedgerDirection,
    WalletLedgerReason,
)
from app.observability.reconciliation_metrics import (
    RECON_DIFF_COUNT,
    RECON_RUN_TOTAL,
    current_env_label,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
NOW = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
# window for NOW = 2026-05-30 21:00 .. 2026-05-31 21:00 UTC
WINDOW_START, WINDOW_END = compute_window(NOW)
IN_WINDOW = WINDOW_START + timedelta(hours=2)
OUT_WINDOW_BEFORE = WINDOW_START - timedelta(hours=2)
OUT_WINDOW_AFTER = WINDOW_END + timedelta(hours=2)


async def _seed_order(
    session,
    *,
    patient_id: uuid.UUID,
    price: Decimal = Decimal("199.00"),
    status: OrderStatus = OrderStatus.completed,
    updated_at: datetime = IN_WINDOW,
) -> Order:
    order = Order(
        order_number=f"ON{uuid.uuid4().hex[:10].upper()}",
        patient_id=patient_id,
        hospital_id=uuid.uuid4(),
        service_type=ServiceType.half_accompany,
        status=status,
        appointment_date="2026-05-30",
        appointment_time="09:00",
        price=price,
        updated_at=updated_at,
    )
    session.add(order)
    await session.flush()
    return order


async def _seed_payment(
    session,
    *,
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    amount: Decimal = Decimal("199.00"),
    payment_type: str = "pay",
    status: str = "success",
    created_at: datetime = IN_WINDOW,
    trade_no: str | None = None,
) -> Payment:
    pay = Payment(
        order_id=order_id,
        user_id=user_id,
        amount=amount,
        payment_type=payment_type,
        status=status,
        trade_no=trade_no or f"T{uuid.uuid4().hex[:10]}",
        created_at=created_at,
    )
    session.add(pay)
    await session.flush()
    return pay


async def _seed_ledger(
    session,
    *,
    user_id: uuid.UUID,
    order_id: uuid.UUID | None,
    amount: Decimal = Decimal("199.00"),
    direction: WalletLedgerDirection = WalletLedgerDirection.in_,
    reason: WalletLedgerReason = WalletLedgerReason.pay,
    occurred_at: datetime = IN_WINDOW,
    provider_txn_id: str | None = None,
) -> WalletLedger:
    row = WalletLedger(
        user_id=user_id,
        order_id=order_id,
        provider_txn_id=provider_txn_id or f"L{uuid.uuid4().hex[:10]}",
        amount=amount,
        direction=direction,
        reason=reason,
        occurred_at=occurred_at,
    )
    session.add(row)
    await session.flush()
    return row


def _diff_count_value(*, kind: str, status: str, provider: str) -> float:
    """Read the latest value of the diff Gauge for these labels."""
    metric = RECON_DIFF_COUNT.labels(
        kind=kind, status=status, provider=provider, env=current_env_label()
    )
    return metric._value.get()


def _run_total_value(*, status: str) -> float:
    metric = RECON_RUN_TOTAL.labels(
        kind="full_t1", status=status, env=current_env_label()
    )
    return metric._value.get()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
async def test_run_with_clean_data_records_success_and_no_diffs(seed_user):
    """Happy path: business / payment / ledger 三源金额一致 → 无 diff。"""
    user = await seed_user(phone="13900100001")
    from tests.conftest import test_session_factory

    runs_before = _run_total_value(status="success")

    async with test_session_factory() as s:
        order = await _seed_order(s, patient_id=user.id)
        await _seed_payment(s, order_id=order.id, user_id=user.id)
        await _seed_ledger(s, user_id=user.id, order_id=order.id)
        await s.commit()

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert isinstance(result, ReconciliationRunResult)
    assert result.status == "success"
    assert result.orders_scanned == 1
    assert result.diffs_found == 0
    assert _run_total_value(status="success") == pytest.approx(runs_before + 1)

    async with test_session_factory() as s:
        run = await s.get(ReconciliationRun, result.run_id)
        assert run is not None
        assert run.status == ReconRunStatus.success
        assert run.finished_at is not None
        diffs = (
            await s.execute(select(ReconciliationDiff).where(ReconciliationDiff.run_id == run.id))
        ).scalars().all()
        assert diffs == []


async def test_run_detects_amount_mismatch(seed_user):
    """Business=199, payment=99 → amount_mismatch + Prometheus gauge 反映。"""
    user = await seed_user(phone="13900100002")
    from tests.conftest import test_session_factory

    async with test_session_factory() as s:
        order = await _seed_order(s, patient_id=user.id, price=Decimal("199.00"))
        await _seed_payment(
            s, order_id=order.id, user_id=user.id, amount=Decimal("99.00")
        )
        await _seed_ledger(s, user_id=user.id, order_id=order.id, amount=Decimal("99.00"))
        await s.commit()

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.status == "success"
    assert result.diffs_found == 1
    # Provider label is whatever settings.payment_provider says (mock by default).
    from app.config import settings as _s

    provider_label = _s.payment_provider or "unknown"
    assert _diff_count_value(
        kind=ReconDiffKind.amount_mismatch.value,
        status="pending",
        provider=provider_label,
    ) >= 1

    async with test_session_factory() as s:
        rows = (
            await s.execute(select(ReconciliationDiff).where(ReconciliationDiff.run_id == result.run_id))
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].kind == ReconDiffKind.amount_mismatch
        assert rows[0].business_amount == Decimal("199.00")
        assert rows[0].payment_amount == Decimal("99.00")


async def test_run_detects_missing_payment(seed_user):
    """Business 期望付款但 payments 表无 success → missing_payment diff。"""
    user = await seed_user(phone="13900100003")
    from tests.conftest import test_session_factory

    async with test_session_factory() as s:
        await _seed_order(s, patient_id=user.id, price=Decimal("299.00"))
        await s.commit()

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.status == "success"
    assert result.diffs_found == 1

    async with test_session_factory() as s:
        rows = (
            await s.execute(select(ReconciliationDiff).where(ReconciliationDiff.run_id == result.run_id))
        ).scalars().all()
        assert rows[0].kind == ReconDiffKind.missing_payment


async def test_window_boundary_excludes_out_of_range_orders(seed_user):
    """窗口外 (>27h 或 <3h) 的订单不应进入本次 run。"""
    user = await seed_user(phone="13900100004")
    from tests.conftest import test_session_factory

    async with test_session_factory() as s:
        # In-window: missing payment → would create a diff
        in_order = await _seed_order(
            s, patient_id=user.id, price=Decimal("100.00"), updated_at=IN_WINDOW
        )
        # Before window: should be ignored
        await _seed_order(
            s,
            patient_id=user.id,
            price=Decimal("100.00"),
            updated_at=OUT_WINDOW_BEFORE,
        )
        # After window: should be ignored
        await _seed_order(
            s,
            patient_id=user.id,
            price=Decimal("100.00"),
            updated_at=OUT_WINDOW_AFTER,
        )
        await s.commit()

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.orders_scanned == 1
    assert result.diffs_found == 1
    assert in_order.id is not None  # sanity


async def test_run_marks_failed_when_query_raises(seed_user, monkeypatch):
    """三源加载抛异常 → run.status='failed'，函数本身不抛到调度器。"""
    user = await seed_user(phone="13900100005")
    from tests.conftest import test_session_factory

    async with test_session_factory() as s:
        order = await _seed_order(s, patient_id=user.id)
        await _seed_payment(s, order_id=order.id, user_id=user.id)
        await s.commit()

    async def _boom(*args, **kwargs):
        raise RuntimeError("simulated db crash")

    monkeypatch.setattr(cron_module, "_load_payment_snapshots", _boom)

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.status == "failed"
    assert "simulated db crash" in (result.last_error or "")

    async with test_session_factory() as s:
        run = await s.get(ReconciliationRun, result.run_id)
        assert run is not None
        assert run.status == ReconRunStatus.failed
        assert run.notes and "simulated db crash" in run.notes


async def test_concurrent_run_skipped_when_lock_not_acquired(seed_user, monkeypatch):
    """模拟另一副本持锁：cron 立即返回 status='skipped'，不写 diff。"""
    user = await seed_user(phone="13900100006")
    from tests.conftest import test_session_factory

    async with test_session_factory() as s:
        order = await _seed_order(s, patient_id=user.id)
        await _seed_payment(s, order_id=order.id, user_id=user.id, amount=Decimal("1.00"))
        await s.commit()

    class _NotAcquiredLock:
        acquired = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(
        cron_module,
        "acquire_scheduler_lock",
        lambda **_: _NotAcquiredLock(),
    )

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.status == "skipped"
    assert result.diffs_found == 0

    async with test_session_factory() as s:
        rows = (
            await s.execute(select(ReconciliationDiff).where(ReconciliationDiff.run_id == result.run_id))
        ).scalars().all()
        assert rows == []


async def test_diff_dedup_within_run(seed_user, monkeypatch):
    """If diff_orders ever returns dup (order_id, kind) the persister skips."""
    user = await seed_user(phone="13900100007")
    from tests.conftest import test_session_factory

    from app.services.reconciliation.diff import ReconDiff

    async with test_session_factory() as s:
        order = await _seed_order(s, patient_id=user.id, price=Decimal("50.00"))
        await s.commit()
        order_id = order.id

    def _fake_diff(*_args, **_kwargs):
        return [
            ReconDiff(order_id=order_id, kind=ReconDiffKind.missing_payment),
            ReconDiff(order_id=order_id, kind=ReconDiffKind.missing_payment),
        ]

    monkeypatch.setattr(cron_module, "diff_orders", _fake_diff)

    async with test_session_factory() as s:
        result = await run_t1_reconciliation(now=NOW, session=s)

    assert result.status == "success"
    assert result.diffs_found == 1
