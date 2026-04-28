"""[ADR-0032 / D-044 Q3] Tests for the OrderService reconciliation guard.

The guard is a *sync* helper that queries ``reconciliation_diffs``. Tests
exercise it via a sync SQLAlchemy session against an in-memory SQLite
database (independent of the suite-wide async fixture so the guard
contract is tested in isolation).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.exceptions import OrderBlockedByReconciliationError
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconciliationRun,
    ReconDiffKind,
    ReconDiffStatus,
    ReconRunKind,
    ReconRunStatus,
)
from app.services.order._recon_guard import check_reconciliation_block


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


@pytest.fixture
def sync_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _make_run(session) -> ReconciliationRun:
    run = ReconciliationRun(
        kind=ReconRunKind.full_t1,
        status=ReconRunStatus.success,
        window_start=datetime(2026, 5, 30, tzinfo=timezone.utc),
        window_end=datetime(2026, 5, 31, tzinfo=timezone.utc),
        triggered_by="test",
    )
    session.add(run)
    session.flush()
    return run


def _make_diff(
    session,
    *,
    order_id: uuid.UUID,
    kind: ReconDiffKind = ReconDiffKind.amount_mismatch,
    status: ReconDiffStatus = ReconDiffStatus.pending,
    created_at: datetime | None = None,
) -> ReconciliationDiff:
    run = _make_run(session)
    diff = ReconciliationDiff(
        run_id=run.id,
        order_id=order_id,
        provider="mock",
        kind=kind,
        status=status,
        business_amount=Decimal("199.00"),
        payment_amount=Decimal("99.00"),
        ledger_amount=Decimal("99.00"),
    )
    if created_at is not None:
        diff.created_at = created_at
    session.add(diff)
    session.flush()
    return diff


def test_guard_allows_when_no_diff_exists(sync_session):
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    # Should simply return None.
    check_reconciliation_block(uuid.uuid4(), sync_session, cutoff)


def test_guard_blocks_on_pending_amount_mismatch(sync_session):
    order_id = uuid.uuid4()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _make_diff(
        sync_session,
        order_id=order_id,
        kind=ReconDiffKind.amount_mismatch,
        status=ReconDiffStatus.pending,
        created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(OrderBlockedByReconciliationError) as exc:
        check_reconciliation_block(order_id, sync_session, cutoff)

    assert exc.value.status_code == 409


def test_guard_blocks_on_mismatched_amount_mismatch(sync_session):
    """status='mismatched' is also a blocker (replay attempted, still bad)."""
    order_id = uuid.uuid4()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _make_diff(
        sync_session,
        order_id=order_id,
        kind=ReconDiffKind.amount_mismatch,
        status=ReconDiffStatus.mismatched,
        created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
    )

    with pytest.raises(OrderBlockedByReconciliationError):
        check_reconciliation_block(order_id, sync_session, cutoff)


def test_guard_exempts_diff_before_cutoff(sync_session):
    """Pre-rollout (historical) diffs do not block the state machine."""
    order_id = uuid.uuid4()
    cutoff = datetime(2026, 5, 1, tzinfo=timezone.utc)
    _make_diff(
        sync_session,
        order_id=order_id,
        kind=ReconDiffKind.amount_mismatch,
        status=ReconDiffStatus.pending,
        created_at=cutoff - timedelta(days=10),
    )
    # Should not raise.
    check_reconciliation_block(order_id, sync_session, cutoff)


def test_guard_does_not_block_on_missing_payment_kind(sync_session):
    """Only amount_mismatch blocks; missing_payment is informational."""
    order_id = uuid.uuid4()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _make_diff(
        sync_session,
        order_id=order_id,
        kind=ReconDiffKind.missing_payment,
        status=ReconDiffStatus.pending,
        created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
    )
    # Should not raise.
    check_reconciliation_block(order_id, sync_session, cutoff)


def test_guard_ignores_closed_diff(sync_session):
    """A diff that has already been resolved (closed/matched/compensated)
    does not block subsequent transitions."""
    order_id = uuid.uuid4()
    cutoff = datetime(2026, 1, 1, tzinfo=timezone.utc)
    _make_diff(
        sync_session,
        order_id=order_id,
        kind=ReconDiffKind.amount_mismatch,
        status=ReconDiffStatus.closed,
        created_at=datetime(2026, 5, 31, 12, 0, tzinfo=timezone.utc),
    )
    check_reconciliation_block(order_id, sync_session, cutoff)
