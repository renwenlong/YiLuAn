"""NotificationOutbox — transactional outbox for reliable notification delivery.

Background
----------
ADR-0058 (notification outbox pattern). Historically ``notify_*`` flows called
``create_notification`` **synchronously inside the business transaction**. If the
downstream push/delivery failed (or the process died mid-flight) the notification
was silently lost, and if the business transaction later rolled back the
notification could still have fired — neither atomic (G1) nor reliable (G2/G3).

The outbox table decouples *intent to notify* from *actual delivery*:

- Business service calls ``enqueue_notification_outbox(session, ...)`` **inside the
  business transaction** → a row is INSERTed with ``status=pending``. The enqueue
  does **not** send anything; it only writes the row. Because it shares the
  business transaction, the outbox row commits/rolls back atomically with the
  business data (G1, AC-1).
- A separate ``notification_outbox_worker`` (DEV-2, not in this task) later picks up
  ``pending`` / due ``failed`` rows and performs the actual delivery with retry +
  dead-letter handling (G2/G3).

Scope note (DEV-1, 反案 #51 boundary)
-------------------------------------
This module ships **only** the table + model + enqueue helper. It does **not**:
- implement the worker (DEV-2),
- modify ``notification.py`` / ``notify_*`` call sites (DEV-3),
- wire the ``NOTIFICATION_OUTBOX_ENABLED`` feature flag (DEV-3).

Schema (ADR-0058 §3.1)
----------------------
- ``event_dedup_key`` is UNIQUE so the same business event cannot be enqueued
  twice (idempotency, AC-5). Duplicate enqueue raises ``IntegrityError``; callers
  decide whether to swallow it (already-queued) — see ``enqueue_notification_outbox``.
- ``payload`` is a notification snapshot (JSONB on Postgres, JSON on SQLite for
  test/dev parity) so new notification shapes do not require a migration.
- Indexed on ``(status, next_retry_at)`` so the worker can efficiently fetch
  ``pending`` and due ``failed`` rows in one scan.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base

# Default retry ceiling before a row is parked as ``dead`` (DEV-2 worker honours
# this; kept here so the column has a stable server-agnostic default). Workers
# may override per-row via ``max_retries``.
DEFAULT_MAX_RETRIES = 5

# Use JSONB on Postgres, fall back to JSON for SQLite (test/dev parity), mirroring
# the dead_letter.py convention so unit tests can run on SQLite.
_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class NotificationOutboxStatus(str, enum.Enum):
    """Lifecycle of an outbox row.

    - ``pending``    — enqueued, awaiting first delivery attempt by the worker
    - ``delivering`` — worker claimed the row (optimistic lock) and is delivering
    - ``delivered``  — delivery succeeded; terminal
    - ``failed``     — a delivery attempt failed; eligible for retry once
      ``next_retry_at`` is due
    - ``dead``       — exhausted ``max_retries``; parked for dead-letter handling
    """

    pending = "pending"
    delivering = "delivering"
    delivered = "delivered"
    failed = "failed"
    dead = "dead"


class NotificationOutbox(Base):
    """A queued notification intent, written atomically with its business event."""

    __tablename__ = "notification_outbox"
    __table_args__ = (
        # Worker hot path: fetch pending + due-failed rows efficiently.
        Index(
            "ix_notification_outbox_status_next_retry",
            "status",
            "next_retry_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Business event unique key (e.g. ``order_status_changed:<order_id>:<status>``)
    # — UNIQUE so the same event cannot be enqueued twice (AC-5 idempotency).
    event_dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Notification content snapshot (user_id / type / title / body / target ...).
    # JSONB on Postgres so new shapes need no migration.
    payload: Mapped[dict] = mapped_column(_JSON_TYPE, nullable=False)
    status: Mapped[NotificationOutboxStatus] = mapped_column(
        Enum(NotificationOutboxStatus, name="notification_outbox_status"),
        default=NotificationOutboxStatus.pending,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=DEFAULT_MAX_RETRIES, nullable=False)
    # Backoff schedule: when a ``failed`` row becomes eligible for retry.
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
