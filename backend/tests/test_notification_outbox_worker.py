"""Unit tests for the notification outbox worker (ADR-0058 DEV-2).

Covers the DEV-2 acceptance criteria for the *delivery* side:

- AC#1 worker wraps everything in ``acquire_scheduler_lock``; when the lock is
  not acquired it processes nothing (asserted via monkeypatched lock factory).
- AC#2 fetch logic selects ``pending`` and due ``failed`` rows only (not
  ``delivered`` / ``dead`` / not-yet-due ``failed``), ordered FIFO.
- AC#3 success -> ``delivered`` + ``delivered_at``; failure -> ``retry_count++``
  and an exponential-backoff ``next_retry_at`` (assert it advances, not a hard
  literal -- backoff params come from config).
- AC#4 at-least-once: a first-attempt failure is retried on a later tick and
  eventually delivered (assert ``retry_count`` increments + terminal
  ``delivered``).
- AC#5 dead-letter: once ``retry_count >= max_retries`` the row goes ``dead``
  and a ``DeadLetter`` row is written via ``record_dead_letter`` (not silently
  dropped).
- AC#6 optimistic-lock claim: ``status -> delivering`` is a conditional UPDATE.

The ``notify_*`` business wiring (DEV-3) is out of scope. We inject a fake
``deliver_fn`` so success/failure can be simulated deterministically; the real
``_default_deliver`` payload->NotificationService dispatch is exercised in
DEV-3 once enqueue writes the agreed payload schema.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.cron import notification_outbox_worker as worker
from app.models.dead_letter import DeadLetter
from app.models.notification_outbox import (
    NotificationOutbox,
    NotificationOutboxStatus,
)
from app.services.notification_outbox import enqueue_notification_outbox

# Use the SQLite async session factory the suite already provides.
from tests.conftest import test_session_factory as _session_factory


@pytest.fixture(autouse=True)
def _patch_worker_session():
    """Point the worker's ``async_session`` at the SQLite test factory.

    The worker builds its own session (no request context); without this it
    would hit the real Postgres DSN (absent in CI) and the PG advisory lock
    would report NOT-acquired -> every tick would skip. Mirrors the
    ai_summary_enqueue worker test setup.
    """
    with patch("app.cron.notification_outbox_worker.async_session", _session_factory):
        yield


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _payload() -> dict:
    return {
        "user_id": str(uuid.uuid4()),
        "type": "order_status_changed",
        "title": "order status updated",
        "body": "your order was accepted",
        "target_type": "order",
        "target_id": str(uuid.uuid4()),
    }


async def _enqueue(session, *, dedup: str | None = None) -> NotificationOutbox:
    dedup = dedup or f"evt:{uuid.uuid4()}"
    row = await enqueue_notification_outbox(session, event_dedup_key=dedup, payload=_payload())
    await session.commit()
    return row


async def _reload(session, row_id) -> NotificationOutbox:
    return (
        await session.execute(select(NotificationOutbox).where(NotificationOutbox.id == row_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# deliver_fn doubles
# ---------------------------------------------------------------------------
async def _deliver_ok(session, row):  # always succeeds
    return None


def _make_flaky(fail_times: int):
    """Fail the first ``fail_times`` calls, succeed afterwards (AC#4)."""
    state = {"n": 0}

    async def _deliver(session, row):
        state["n"] += 1
        if state["n"] <= fail_times:
            raise RuntimeError(f"simulated delivery failure #{state['n']}")
        return None

    return _deliver


async def _deliver_always_fail(session, row):
    raise RuntimeError("permanent downstream outage")


# ---------------------------------------------------------------------------
# AC#3 backoff formula
# ---------------------------------------------------------------------------
def test_compute_next_retry_at_is_exponential():
    """Backoff grows exponentially and is capped (AC#3, params from config)."""
    base = worker.settings.notification_outbox_backoff_base_seconds
    factor = worker.settings.notification_outbox_backoff_factor
    cap = worker.settings.notification_outbox_backoff_cap_seconds
    now = _now()

    d1 = (worker._compute_next_retry_at(1, now=now) - now).total_seconds()
    d2 = (worker._compute_next_retry_at(2, now=now) - now).total_seconds()
    d3 = (worker._compute_next_retry_at(3, now=now) - now).total_seconds()

    # retry 1 -> base*factor^0 = base; retry 2 -> base*factor^1; strictly growing.
    assert d1 == pytest.approx(min(base, cap))
    assert d2 == pytest.approx(min(base * factor, cap))
    assert d3 == pytest.approx(min(base * factor * factor, cap))
    assert d1 <= d2 <= d3

    # A very large retry_count is capped, never unbounded.
    d_big = (worker._compute_next_retry_at(50, now=now) - now).total_seconds()
    assert d_big == pytest.approx(cap)


# ---------------------------------------------------------------------------
# AC#2 fetch logic
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_fetch_selects_pending_and_due_failed_only():
    """Only pending + due failed are fetched; delivered/dead/not-due excluded."""
    now = _now()
    async with _session_factory() as session:
        r_pending = await _enqueue(session)

        r_failed_due = await _enqueue(session)
        r_failed_due.status = NotificationOutboxStatus.failed
        r_failed_due.next_retry_at = now - timedelta(seconds=10)

        r_failed_future = await _enqueue(session)
        r_failed_future.status = NotificationOutboxStatus.failed
        r_failed_future.next_retry_at = now + timedelta(hours=1)

        r_delivered = await _enqueue(session)
        r_delivered.status = NotificationOutboxStatus.delivered

        r_dead = await _enqueue(session)
        r_dead.status = NotificationOutboxStatus.dead

        await session.commit()

        rows = await worker._fetch_due_rows(session, limit=50, now=now)
        ids = {r.id for r in rows}

    assert r_pending.id in ids
    assert r_failed_due.id in ids
    assert r_failed_future.id not in ids
    assert r_delivered.id not in ids
    assert r_dead.id not in ids


@pytest.mark.asyncio
async def test_fetch_respects_batch_limit():
    """Batch size caps how many rows a single tick claims (AC#2)."""
    async with _session_factory() as session:
        for _ in range(5):
            await _enqueue(session)
        rows = await worker._fetch_due_rows(session, limit=3)
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# AC#3 success path
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliver_success_marks_delivered():
    """Successful delivery -> delivered + delivered_at set, error cleared (AC#3)."""
    async with _session_factory() as session:
        row = await _enqueue(session)

    result = await worker.process_notification_outbox_job(deliver_fn=_deliver_ok)

    async with _session_factory() as session:
        reloaded = await _reload(session, row.id)

    assert result["status"] == "ok"
    assert result["delivered"] == 1
    assert reloaded.status is NotificationOutboxStatus.delivered
    assert reloaded.delivered_at is not None
    assert reloaded.last_error is None


# ---------------------------------------------------------------------------
# AC#3 failure path -> retry with backoff
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_deliver_failure_increments_retry_and_schedules_backoff():
    """Failure -> status=failed, retry_count=1, next_retry_at in the future (AC#3)."""
    before = _now()
    async with _session_factory() as session:
        row = await _enqueue(session)

    result = await worker.process_notification_outbox_job(deliver_fn=_deliver_always_fail)

    async with _session_factory() as session:
        reloaded = await _reload(session, row.id)

    assert result["retried"] == 1
    assert reloaded.status is NotificationOutboxStatus.failed
    assert reloaded.retry_count == 1
    assert reloaded.last_error is not None
    assert reloaded.next_retry_at is not None
    # backoff schedules into the future. SQLite reads timestamps back tz-naive,
    # so normalize both sides before comparing (the exact delay is asserted in
    # test_compute_next_retry_at; here we only check it advances).
    nra = reloaded.next_retry_at
    if nra.tzinfo is None:
        nra = nra.replace(tzinfo=timezone.utc)
    assert nra > before


# ---------------------------------------------------------------------------
# AC#4 at-least-once: fail then retry then deliver
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_at_least_once_retry_then_eventually_delivered():
    """First tick fails, a later tick (after due) retries and delivers (AC#4)."""
    flaky = _make_flaky(fail_times=1)
    async with _session_factory() as session:
        row = await _enqueue(session)

    # tick 1: fails -> failed, retry_count=1, next_retry_at future
    r1 = await worker.process_notification_outbox_job(deliver_fn=flaky)
    assert r1["retried"] == 1

    async with _session_factory() as session:
        mid = await _reload(session, row.id)
        assert mid.status is NotificationOutboxStatus.failed
        assert mid.retry_count == 1
        # simulate time passing: make it due now
        mid.next_retry_at = _now() - timedelta(seconds=1)
        await session.commit()

    # tick 2: succeeds -> delivered, retry_count stays 1
    r2 = await worker.process_notification_outbox_job(deliver_fn=flaky)
    assert r2["delivered"] == 1

    async with _session_factory() as session:
        final = await _reload(session, row.id)

    assert final.status is NotificationOutboxStatus.delivered
    assert final.delivered_at is not None
    assert final.retry_count == 1  # incremented once, not reset


# ---------------------------------------------------------------------------
# AC#5 dead-letter on exhaustion
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_dead_letter_when_retries_exhausted():
    """retry_count reaching max_retries -> dead + DeadLetter row written (AC#5)."""
    async with _session_factory() as session:
        row = await _enqueue(session)
        # Pre-age it to the last allowed attempt: next failure hits max_retries.
        row.retry_count = row.max_retries - 1
        await session.commit()

    result = await worker.process_notification_outbox_job(deliver_fn=_deliver_always_fail)

    async with _session_factory() as session:
        reloaded = await _reload(session, row.id)
        dl = (
            (await session.execute(select(DeadLetter).where(DeadLetter.channel == "notification")))
            .scalars()
            .all()
        )

    assert result["dead"] == 1
    assert reloaded.status is NotificationOutboxStatus.dead
    assert reloaded.retry_count == reloaded.max_retries
    assert len(dl) == 1
    assert dl[0].reason == "delivery_exhausted"
    assert dl[0].payload["outbox_id"] == str(row.id)


# ---------------------------------------------------------------------------
# AC#6 optimistic-lock claim
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_claim_row_is_conditional_update():
    """_claim_row flips pending->delivering via conditional UPDATE (AC#6).

    A racer that still believes the row is ``pending`` issues the same
    conditional UPDATE (``WHERE status=pending``); once the row is already
    ``delivering`` that UPDATE matches 0 rows, so the racer's claim fails.
    Separate sessions avoid the identity-map sharing the same instance.
    """
    async with _session_factory() as session:
        row = await _enqueue(session)
        row_id = row.id

    # Winner claims in its own session: pending -> delivering (1 row).
    async with _session_factory() as s_winner:
        winner_row = await _reload(s_winner, row_id)
        won = await worker._claim_row(s_winner, winner_row)
        await s_winner.commit()
        assert won is True

    # Confirm it is now delivering in the DB.
    async with _session_factory() as s_check:
        assert (await _reload(s_check, row_id)).status is NotificationOutboxStatus.delivering

    # Racer holds a stale expected=pending; conditional UPDATE matches 0 rows.
    # ``no_autoflush`` prevents the forced in-memory ``pending`` from being
    # flushed back to the DB before the conditional UPDATE evaluates.
    async with _session_factory() as s_racer:
        racer_row = await _reload(s_racer, row_id)
        racer_row.status = NotificationOutboxStatus.pending  # stale expected
        with s_racer.no_autoflush:
            lost = await worker._claim_row(s_racer, racer_row)
        await s_racer.rollback()

    assert lost is False


# ---------------------------------------------------------------------------
# AC#1 scheduler-lock: not acquired -> process nothing
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_skips_when_scheduler_lock_not_acquired(monkeypatch):
    """When the scheduler lock is not acquired, the worker processes nothing (AC#1)."""

    class _NotAcquiredLock:
        acquired = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

    def _fake_acquire(**kwargs):
        return _NotAcquiredLock()

    monkeypatch.setattr(worker, "acquire_scheduler_lock", _fake_acquire)

    async with _session_factory() as session:
        row = await _enqueue(session)

    # deliver_fn injected (would deliver) -- but lock blocks all work.
    result = await worker.process_notification_outbox_job(deliver_fn=_deliver_ok)

    async with _session_factory() as session:
        reloaded = await _reload(session, row.id)

    assert result["status"] == "skipped"
    assert result["processed"] == 0
    assert reloaded.status is NotificationOutboxStatus.pending  # untouched
