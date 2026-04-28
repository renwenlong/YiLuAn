"""[ADR-0032 / D-044 Q3] Order state-machine guard against unresolved
``amount_mismatch`` reconciliation diffs.

This module provides a single helper, :func:`check_reconciliation_block`,
that callers (today: nobody; M3: ``OrderService.transition``) invoke
before mutating order state. It raises
:class:`~app.exceptions.OrderBlockedByReconciliationError` (HTTP 409)
when a blocking diff exists.

Design notes
------------
* **Only ``amount_mismatch`` blocks.** ``missing_payment`` /
  ``orphan_payment`` / ``status_mismatch`` are surfaced via dashboards but
  do not freeze the state machine — they can usually be resolved without
  touching the order itself.
* **Historical exemption** (``cutoff``): diffs created **before**
  ``settings.reconciliation_cutoff`` are treated as already-grandfathered
  and never block. This is the upgrade safety valve so M2 deploy doesn't
  retroactively freeze pre-existing orders that happened to have a stale
  diff lying around.
* **Synchronous + sync ``Session``** on purpose: the current order
  service uses :class:`sqlalchemy.ext.asyncio.AsyncSession`; M3 wiring
  will adapt to the calling site. We expose a sync version here so the
  guard can also be used by admin scripts / batch jobs.

This file is intentionally **not** imported by ``OrderService.transition``
in M2 — M2 ships the guard + unit tests only. M3 wires it into the state
machine in a small follow-up PR.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.exceptions import OrderBlockedByReconciliationError
from app.models.reconciliation import (
    ReconciliationDiff,
    ReconDiffKind,
    ReconDiffStatus,
)


_BLOCKING_STATUSES: frozenset[ReconDiffStatus] = frozenset(
    {ReconDiffStatus.pending, ReconDiffStatus.mismatched}
)
_BLOCKING_KINDS: frozenset[ReconDiffKind] = frozenset(
    {ReconDiffKind.amount_mismatch}
)


def check_reconciliation_block(
    order_id: UUID,
    db: Session,
    cutoff: datetime,
) -> None:
    """Raise if ``order_id`` has any blocking diff newer than ``cutoff``.

    Parameters
    ----------
    order_id:
        The order under inspection.
    db:
        A *sync* SQLAlchemy ``Session``. Async callers can wrap a
        ``run_sync`` invocation around this helper.
    cutoff:
        Diffs whose ``created_at`` is **strictly less than** ``cutoff`` are
        ignored (historical exemption). Must be timezone-aware; naive
        datetimes are coerced to UTC.

    Raises
    ------
    OrderBlockedByReconciliationError:
        If at least one matching diff exists.
    """
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)

    stmt = (
        select(ReconciliationDiff.id)
        .where(ReconciliationDiff.order_id == order_id)
        .where(ReconciliationDiff.kind.in_(_iter_values(_BLOCKING_KINDS)))
        .where(ReconciliationDiff.status.in_(_iter_values(_BLOCKING_STATUSES)))
        .where(ReconciliationDiff.created_at >= cutoff)
        .limit(1)
    )
    row = db.execute(stmt).first()
    if row is not None:
        raise OrderBlockedByReconciliationError(
            f"Order {order_id} has an unresolved amount_mismatch diff",
        )


def _iter_values(items: Iterable) -> list:
    """Allow callers to pass either Enum members or raw strings."""
    return [getattr(i, "value", i) for i in items]
