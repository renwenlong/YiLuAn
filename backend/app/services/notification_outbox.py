"""Notification outbox service — ``enqueue_notification_outbox`` helper.

ADR-0058 (notification outbox pattern), DEV-1.

This is the *write* side of the outbox: business services call
``enqueue_notification_outbox`` **inside their business transaction** to queue a
notification intent. The actual delivery is performed later by the
``notification_outbox_worker`` (DEV-2, not in this task).

Atomicity contract (G1, AC-1)
-----------------------------
Unlike ``dead_letter.record_dead_letter`` (which is *best-effort* because the
primary transition already succeeded), the outbox enqueue is **part of** the
business transaction:

- The row is ``session.add``-ed to the caller's session and shares its
  transaction. If the business transaction commits, the outbox row commits with
  it; if the business transaction rolls back, the outbox row rolls back too. The
  helper therefore does **not** commit on its own.
- We intentionally do **not** swallow arbitrary errors (that would break the
  atomicity guarantee — a failed enqueue must surface so the business flow can
  react).

Dedup handling (AC-5 idempotency)
---------------------------------
``event_dedup_key`` is UNIQUE at the DB level (the ultimate guard). On top of
that, when ``ignore_duplicate`` is set the helper does a cheap ``SELECT`` pre-check
and skips the INSERT if the key already exists, returning ``None``. This keeps the
caller's transaction clean for the common "already queued" case **without** a
SAVEPOINT — a deliberate choice because ``begin_nested()`` SAVEPOINTs do not
reliably roll back under the async SQLite driver used in tests (the row would
escape an outer rollback, breaking the G1 atomicity guarantee). The DB UNIQUE
constraint still backstops the rare concurrent-insert race; in that race the
second INSERT raises ``IntegrityError`` and the caller is expected to handle it
(its transaction is then dirty, same as any constraint violation).

Scope note (DEV-1, 反案 #51 boundary)
-------------------------------------
Only the enqueue helper lives here. The worker (DEV-2), the ``notify_*`` call-site
changes and the ``NOTIFICATION_OUTBOX_ENABLED`` flag (DEV-3) are out of scope.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification_outbox import (
    NotificationOutbox,
    NotificationOutboxStatus,
)

logger = logging.getLogger("app.services.notification_outbox")


async def enqueue_notification_outbox(
    session: AsyncSession,
    *,
    event_dedup_key: str,
    payload: dict[str, Any],
    ignore_duplicate: bool = True,
    flush: bool = True,
) -> NotificationOutbox | None:
    """Queue a notification intent inside the caller's business transaction.

    The row is added to ``session`` (status ``pending``) and shares the caller's
    transaction — it is **not** committed here, so it commits/rolls back atomically
    with the business data (G1, AC-1). Delivery happens later in the worker (DEV-2).

    Parameters
    ----------
    session:
        The caller's *business* session. The outbox row joins this transaction.
    event_dedup_key:
        Stable unique key for the business event (e.g.
        ``order_status_changed:<order_id>:<new_status>``). Enforced UNIQUE at the
        DB level so the same event cannot be enqueued twice (AC-5).
    payload:
        JSON-serialisable notification snapshot (user_id / type / title / body /
        target ...). Stored as JSONB on Postgres.
    ignore_duplicate:
        When True (default) a dedup-key collision is treated as a benign
        "already queued" no-op and ``None`` is returned (the existing row is left
        untouched): a cheap ``SELECT`` pre-check skips the INSERT. When False the
        pre-check is skipped and any ``IntegrityError`` propagates so the caller
        can handle it explicitly.
    flush:
        When True (default) flush so the row gets an ``id`` (and a duplicate
        INSERT, if any slipped past the pre-check via a race, surfaces now).
        Disable only in batch paths that flush later.

    Returns
    -------
    The inserted ``NotificationOutbox`` row, or ``None`` when a duplicate was
    ignored (``ignore_duplicate=True`` and the key already exists).
    """
    if ignore_duplicate:
        # Cheap pre-check: if the event is already queued, no-op without an
        # INSERT so the caller's transaction stays clean (no SAVEPOINT needed).
        existing = (
            await session.execute(
                select(NotificationOutbox.id).where(
                    NotificationOutbox.event_dedup_key == event_dedup_key
                )
            )
        ).first()
        if existing is not None:
            logger.info(
                "notification_outbox_enqueue_duplicate dedup_key=%s (ignored)",
                event_dedup_key,
            )
            return None

    row = NotificationOutbox(
        event_dedup_key=event_dedup_key,
        payload=payload,
        status=NotificationOutboxStatus.pending,
    )
    session.add(row)
    if flush:
        # Surfaces a (racing) duplicate INSERT as IntegrityError; for the normal
        # path it just assigns the row id.
        await session.flush()
    return row
