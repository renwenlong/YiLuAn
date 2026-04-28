"""[ADR-0032 / D-044 Q3 / M3] Tests for the async OrderService.transition guard wiring.

Covers `check_reconciliation_block_async` and the integration via
`OrderService._check_recon_block` (called from lifecycle / cancel
methods).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.exceptions import OrderBlockedByReconciliationError
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.services.order._recon_guard import check_reconciliation_block_async
from tests.conftest import test_session_factory


pytestmark = pytest.mark.asyncio


async def _seed_blocking_diff(s, order_id, *, kind=ReconDiffKind.amount_mismatch,
                              status=ReconDiffStatus.pending,
                              created_at: datetime | None = None):
    now = datetime.now(timezone.utc)
    run = ReconciliationRun(
        kind=ReconRunKind.full_t1,
        status=ReconRunStatus.success,
        window_start=now - timedelta(days=1),
        window_end=now,
        triggered_by="test",
    )
    s.add(run)
    await s.flush()
    diff = ReconciliationDiff(
        run_id=run.id,
        order_id=order_id,
        provider="wechat",
        kind=kind,
        status=status,
        business_amount=Decimal("100.00"),
        payment_amount=Decimal("99.00"),
        ledger_amount=Decimal("100.00"),
    )
    s.add(diff)
    await s.flush()
    if created_at is not None:
        diff.created_at = created_at
        await s.flush()
    return diff


async def test_async_guard_blocks_amount_mismatch():
    order_id = uuid.uuid4()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with test_session_factory() as s:
        await _seed_blocking_diff(s, order_id, kind=ReconDiffKind.amount_mismatch)
        await s.commit()
        with pytest.raises(OrderBlockedByReconciliationError) as exc:
            await check_reconciliation_block_async(order_id, s, cutoff)
    assert "ORDER_BLOCKED_BY_RECONCILIATION" == exc.value.error_code
    assert exc.value.status_code == 409


async def test_async_guard_passes_when_no_diff():
    order_id = uuid.uuid4()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with test_session_factory() as s:
        await check_reconciliation_block_async(order_id, s, cutoff)


async def test_async_guard_ignores_non_blocking_kind():
    """Only amount_mismatch is blocking; missing_payment should NOT raise."""
    order_id = uuid.uuid4()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with test_session_factory() as s:
        await _seed_blocking_diff(s, order_id, kind=ReconDiffKind.missing_payment)
        await s.commit()
        await check_reconciliation_block_async(order_id, s, cutoff)


async def test_async_guard_ignores_resolved_status():
    order_id = uuid.uuid4()
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    async with test_session_factory() as s:
        await _seed_blocking_diff(
            s, order_id,
            kind=ReconDiffKind.amount_mismatch,
            status=ReconDiffStatus.compensated,
        )
        await s.commit()
        await check_reconciliation_block_async(order_id, s, cutoff)


async def test_async_guard_exempts_diff_older_than_cutoff():
    """D-044 Q3: diffs created before settings.reconciliation_cutoff are exempted."""
    order_id = uuid.uuid4()
    # Cutoff is "now - 7d"; the diff is from 30 days ago → exempt
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    old_ts = datetime.now(timezone.utc) - timedelta(days=30)
    async with test_session_factory() as s:
        await _seed_blocking_diff(s, order_id, created_at=old_ts)
        await s.commit()
        await check_reconciliation_block_async(order_id, s, cutoff)
