"""Unit tests for the notification outbox business integration + feature flag
(ADR-0058 DEV-3, S3-DEV-OUTBOX-3-INTEGRATION-FLAG).

Covers the DEV-3 acceptance criteria for the *business wiring* side:

- AC#0 payload schema contract (the hard constraint DEV-2's worker imposes):
  the payload that ``notify_*`` enqueues, when fed to the worker's
  ``_default_deliver``, deserialises cleanly into a successful
  ``create_notification`` -- no ``KeyError`` / ``ValueError``. This is the
  end-to-end schema-alignment test the worker suite deferred to DEV-3.
- AC#1 ``NOTIFICATION_OUTBOX_ENABLED`` defaults to ``False`` (old synchronous
  ``create_notification`` path, current behaviour unchanged).
- AC#2 flag True -> ``notify_*`` calls ``enqueue_notification_outbox`` (writes
  an outbox row inside the business transaction, no synchronous delivery).
- AC#3 grey-release toggle: both flag False<->True paths verified.
- AC#5 business-not-polluted: with flag True a *delivery-side* failure does not
  roll back the business transaction (the enqueue commit is independent).
- AC#6 async non-blocking: flag True only writes the outbox row (no real
  delivery latency on the business call path).

The flag is read at call time off ``app.config.settings`` so tests toggle it
via ``monkeypatch.setattr``. We exercise the *real* ``_default_deliver`` to
prove the round-trip, mirroring the worker's deserialisation exactly.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.config import settings
from app.cron import notification_outbox_worker as worker
from app.models.notification import (
    Notification,
    NotificationTargetType,
    NotificationType,
)
from app.models.notification_outbox import (
    NotificationOutbox,
    NotificationOutboxStatus,
)
from app.services.notification import NotificationService

# SQLite async session factory the suite already provides (alias avoids the
# pytest collect-by-name trap on a non-callable module-level symbol).
from tests.conftest import test_session_factory as _session_factory

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _Order:
    """Minimal duck-typed order for notify_* methods (they only read a few
    attrs: id / order_number / patient_name / appointment_* / hospital_name)."""

    def __init__(self):
        self.id = uuid.uuid4()
        self.order_number = "ORD-20260625-0001"
        self.patient_name = "张三"
        self.appointment_date = "2026-06-26"
        self.appointment_time = "09:00"
        self.hospital_name = "示例医院"
        self.service_name_snapshot = "全程陪诊"


async def _count(session, model, **where):
    stmt = select(func.count()).select_from(model)
    for k, v in where.items():
        stmt = stmt.where(getattr(model, k) == v)
    return (await session.execute(stmt)).scalar_one()


# ---------------------------------------------------------------------------
# AC#1 — flag defaults to False
# ---------------------------------------------------------------------------
async def test_ac1_flag_defaults_false():
    # The shipped default must be False so production behaviour is unchanged
    # until ops explicitly flips it (grey release).
    assert settings.notification_outbox_enabled is False


# ---------------------------------------------------------------------------
# AC#2 / AC#4 — flag False keeps the old synchronous create_notification path
# ---------------------------------------------------------------------------
async def test_ac2_flag_false_writes_notification_not_outbox(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", False)
    async with _session_factory() as session:
        svc = NotificationService(session)
        recipient = uuid.uuid4()
        result = await svc.notify_order_status_changed(_Order(), "accepted", recipient)
        await session.commit()

        # Old path: a real Notification row is created and returned.
        assert isinstance(result, Notification)
        assert await _count(session, Notification, user_id=recipient) == 1
        # And nothing landed in the outbox.
        assert await _count(session, NotificationOutbox) == 0


# ---------------------------------------------------------------------------
# AC#2 / AC#6 — flag True enqueues an outbox row, no synchronous Notification
# ---------------------------------------------------------------------------
async def test_ac2_flag_true_enqueues_outbox_only(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        recipient = uuid.uuid4()
        result = await svc.notify_order_status_changed(_Order(), "accepted", recipient)
        await session.commit()

        # flag True path: no synchronous Notification (delivery is deferred).
        assert result is None
        assert await _count(session, Notification, user_id=recipient) == 0
        # Exactly one outbox row, status pending (worker will drain it later).
        assert await _count(session, NotificationOutbox) == 1
        row = (await session.execute(select(NotificationOutbox))).scalar_one()
        assert row.status == NotificationOutboxStatus.pending
        # AC#0 payload shape: required fields present + correct serialisation.
        assert row.payload["user_id"] == str(recipient)
        assert row.payload["type"] == NotificationType.order_status_changed.value
        assert row.payload["target_type"] == NotificationTargetType.order.value


# ---------------------------------------------------------------------------
# AC#0 — payload schema contract: enqueued payload round-trips through the
# worker's real _default_deliver into a successful create_notification.
# ---------------------------------------------------------------------------
async def test_ac0_payload_roundtrips_through_worker_deliver(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        recipient = uuid.uuid4()
        # Enqueue via the business entrypoint (writes the agreed payload).
        await svc.notify_order_status_changed(_Order(), "completed", recipient)
        await session.commit()

        row = (await session.execute(select(NotificationOutbox))).scalar_one()

        # Feed the SAME row to the worker's real deserialiser. If the payload
        # schema is misaligned this raises KeyError/ValueError -> test fails.
        await worker._default_deliver(session, row)
        await session.commit()

        # Delivery produced exactly the notification the business intended.
        notif = (
            await session.execute(select(Notification).where(Notification.user_id == recipient))
        ).scalar_one()
        assert notif.type == NotificationType.order_status_changed
        assert notif.target_type == NotificationTargetType.order
        assert notif.target_id == str(row.payload["target_id"])


# ---------------------------------------------------------------------------
# AC#0 (breadth) — payloads from several notify_* methods all deserialise.
# ---------------------------------------------------------------------------
async def test_ac0_multiple_notify_methods_payloads_valid(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        order = _Order()
        recipient = uuid.uuid4()
        companion = uuid.uuid4()

        # A representative spread across target types / NotificationType values.
        await svc.notify_order_status_changed(order, "accepted", recipient)
        await svc.notify_new_message(order.id, "李四", recipient)
        await svc.notify_new_order(order, companion)
        await svc.notify_review_received(companion, "王五", order.id, 5, review_id=uuid.uuid4())
        await svc.notify_companion_audit_result(companion, uuid.uuid4(), True)
        await session.commit()

        rows = (await session.execute(select(NotificationOutbox))).scalars().all()
        assert len(rows) == 5

        # Every enqueued payload must survive the worker deserialiser.
        for row in rows:
            await worker._default_deliver(session, row)
        await session.commit()

        # 5 notifications materialised (one per enqueued intent).
        assert await _count(session, Notification) == 5


# ---------------------------------------------------------------------------
# AC#5 — business transaction is isolated from delivery-side failures.
# A row enqueued + committed by the business txn stays put even if a later
# delivery attempt blows up; the business data is never rolled back.
# ---------------------------------------------------------------------------
async def test_ac5_business_txn_isolated_from_delivery_failure(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        recipient = uuid.uuid4()
        await svc.notify_order_status_changed(_Order(), "accepted", recipient)
        # Business commit succeeds independently of any delivery outcome.
        await session.commit()

        row = (await session.execute(select(NotificationOutbox))).scalar_one()

        # Simulate a delivery-side failure (e.g. malformed/unsupported field).
        bad = dict(row.payload)
        bad["type"] = "definitely-not-a-valid-type"
        row.payload = bad
        with pytest.raises(ValueError):
            await worker._default_deliver(session, row)

        # The business-enqueued outbox row is still committed/persisted: the
        # delivery failure did not poison the business transaction.
        await session.rollback()
        assert await _count(session, NotificationOutbox) == 1


# ---------------------------------------------------------------------------
# AC#3 — grey-release toggle: both directions take the correct path.
# ---------------------------------------------------------------------------
async def test_ac3_flag_toggle_switches_path(monkeypatch):
    # First False -> Notification, no outbox.
    monkeypatch.setattr(settings, "notification_outbox_enabled", False)
    async with _session_factory() as session:
        svc = NotificationService(session)
        r1 = uuid.uuid4()
        out = await svc.notify_order_expired(_Order(), r1)
        await session.commit()
        assert isinstance(out, Notification)
        assert await _count(session, NotificationOutbox) == 0

    # Then True -> outbox, no synchronous Notification.
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        r2 = uuid.uuid4()
        out = await svc.notify_order_expired(_Order(), r2)
        await session.commit()
        assert out is None
        assert await _count(session, NotificationOutbox) == 1
        assert await _count(session, Notification, user_id=r2) == 0


# ---------------------------------------------------------------------------
# dedup — same business event enqueued twice is a benign no-op (UNIQUE key).
# ---------------------------------------------------------------------------
async def test_enqueue_dedup_same_event_noop(monkeypatch):
    monkeypatch.setattr(settings, "notification_outbox_enabled", True)
    async with _session_factory() as session:
        svc = NotificationService(session)
        order = _Order()
        recipient = uuid.uuid4()
        # Same (type, user, reference) twice -> identical dedup key.
        await svc.notify_order_status_changed(order, "accepted", recipient)
        await svc.notify_order_status_changed(order, "accepted", recipient)
        await session.commit()
        # Only one row survived the UNIQUE dedup guard.
        assert await _count(session, NotificationOutbox) == 1
