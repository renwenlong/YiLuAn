"""Unit tests for the notification outbox (ADR-0058 DEV-1).

Covers the DEV-1 acceptance criteria for the *write* side:

- enqueue inserts a ``pending`` row that shares the caller's transaction
  (G1 atomicity, AC-1): committing persists it, rolling back discards it;
- ``event_dedup_key`` uniqueness gives idempotent enqueue (AC-5): a duplicate
  is a benign no-op by default and re-raises when ``ignore_duplicate=False``;
- payload round-trips through the JSON(B)/SQLite column.

The worker (DEV-2) and ``notify_*`` wiring (DEV-3) are out of scope and not tested
here.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.notification_outbox import (
    DEFAULT_MAX_RETRIES,
    NotificationOutbox,
    NotificationOutboxStatus,
)
from app.services.notification_outbox import enqueue_notification_outbox

# Use the SQLite async session factory the suite already provides.
from tests.conftest import test_session_factory as _session_factory


def _payload() -> dict:
    return {
        "user_id": str(uuid.uuid4()),
        "type": "order_status_changed",
        "title": "订单状态更新",
        "body": "您的订单已被接单",
        "target_type": "order",
        "target_id": str(uuid.uuid4()),
    }


@pytest.mark.asyncio
async def test_enqueue_inserts_pending_row():
    """Basic enqueue: returns a row with status=pending and a flushed id."""
    dedup = f"order_status_changed:{uuid.uuid4()}:accepted"
    payload = _payload()

    async with _session_factory() as session:
        row = await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=payload)
        await session.commit()

        assert row is not None
        assert row.id is not None  # flush=True gave it an id
        assert row.status is NotificationOutboxStatus.pending
        assert row.retry_count == 0
        assert row.max_retries == DEFAULT_MAX_RETRIES
        assert row.next_retry_at is None
        assert row.delivered_at is None
        assert row.event_dedup_key == dedup
        assert row.payload == payload


@pytest.mark.asyncio
async def test_enqueue_payload_round_trips():
    """Payload is persisted and read back intact from the DB."""
    dedup = f"new_message:{uuid.uuid4()}"
    payload = _payload()

    async with _session_factory() as session:
        await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=payload)
        await session.commit()

    async with _session_factory() as session:
        fetched = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.event_dedup_key == dedup)
            )
        ).scalar_one()
        assert fetched.payload == payload
        assert fetched.status is NotificationOutboxStatus.pending


@pytest.mark.asyncio
async def test_enqueue_is_atomic_with_business_transaction_rollback():
    """G1/AC-1: rolling back the business transaction discards the outbox row.

    The enqueue does not commit on its own — it joins the caller's transaction.
    """
    dedup = f"review_received:{uuid.uuid4()}"

    async with _session_factory() as session:
        row = await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=_payload())
        assert row is not None
        # Simulate the business transaction failing after enqueue.
        await session.rollback()

    # New session: the row must NOT be present (rolled back atomically).
    async with _session_factory() as session:
        found = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.event_dedup_key == dedup)
            )
        ).scalar_one_or_none()
        assert found is None


@pytest.mark.asyncio
async def test_enqueue_commits_persist_the_row():
    """The row is durable only after the caller commits (intent persisted)."""
    dedup = f"new_order:{uuid.uuid4()}"

    async with _session_factory() as session:
        await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=_payload())
        await session.commit()

    async with _session_factory() as session:
        found = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.event_dedup_key == dedup)
            )
        ).scalar_one_or_none()
        assert found is not None


@pytest.mark.asyncio
async def test_enqueue_duplicate_dedup_key_ignored_by_default():
    """AC-5: a duplicate dedup key is a benign no-op (returns None) by default.

    The original row is left intact and the surrounding transaction is not
    poisoned (the conflicting INSERT is rolled back inside a SAVEPOINT).
    """
    dedup = f"order_status_changed:{uuid.uuid4()}:completed"
    first_payload = _payload()
    second_payload = _payload()  # different content, same dedup key

    async with _session_factory() as session:
        first = await enqueue_notification_outbox(
            session, event_dedup_key=dedup, payload=first_payload
        )
        await session.commit()
        assert first is not None

    async with _session_factory() as session:
        dup = await enqueue_notification_outbox(
            session, event_dedup_key=dedup, payload=second_payload
        )
        # SAVEPOINT-guarded duplicate → no-op, transaction still usable.
        assert dup is None
        await session.commit()

    # Exactly one row, still the original payload.
    async with _session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(NotificationOutbox).where(NotificationOutbox.event_dedup_key == dedup)
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload == first_payload


@pytest.mark.asyncio
async def test_enqueue_duplicate_raises_when_not_ignored():
    """AC-5: with ignore_duplicate=False the IntegrityError surfaces to caller."""
    dedup = f"system:{uuid.uuid4()}"

    async with _session_factory() as session:
        await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=_payload())
        await session.commit()

    async with _session_factory() as session:
        with pytest.raises(IntegrityError):
            await enqueue_notification_outbox(
                session,
                event_dedup_key=dedup,
                payload=_payload(),
                ignore_duplicate=False,
            )


@pytest.mark.asyncio
async def test_enqueue_no_flush_defers_id_and_adds_to_session():
    """flush=False adds the row without flushing (caller batches the flush)."""
    dedup = f"start_service_request:{uuid.uuid4()}"

    async with _session_factory() as session:
        row = await enqueue_notification_outbox(
            session, event_dedup_key=dedup, payload=_payload(), flush=False
        )
        assert row is not None
        assert row in session  # added to the session, not yet flushed
        await session.commit()

    async with _session_factory() as session:
        found = (
            await session.execute(
                select(NotificationOutbox).where(NotificationOutbox.event_dedup_key == dedup)
            )
        ).scalar_one_or_none()
        assert found is not None
