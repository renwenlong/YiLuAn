"""DeadLetter — operations queue for failed automatic side-effects.

Background
----------
Some flows (e.g. auto-refund inside ``cancel.py::reject_order``) catch a
provider/business failure and intentionally do **not** block the primary
state transition. Historically those failures were only logged, leaving
ops with no structured worklist to compensate them.

This table is that worklist. A row is written whenever an asynchronous
or best-effort side-effect fails and a human (or a future replay cron)
needs to take action. The schema is intentionally small — `payload` is
JSON so callers can capture whatever context they need without a new
migration each time.

Lifecycle
---------
- ``pending``  — newly created, awaiting human/cron action
- ``resolved`` — operator marked as handled (with reason)

Indexed on ``(status, created_at)`` so the admin queue endpoint can
page through the open backlog efficiently.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    Index,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class DeadLetterStatus(str, enum.Enum):
    pending = "pending"
    resolved = "resolved"


# Use JSONB on Postgres, fall back to JSON for SQLite (test/dev parity).
_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class DeadLetter(Base):
    """Failed side-effect queued for manual / cron compensation."""

    __tablename__ = "dead_letters"
    __table_args__ = (
        Index("ix_dead_letters_status_created", "status", "created_at"),
        Index("ix_dead_letters_channel", "channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Logical channel — e.g. ``order_refund``, ``notification`` — so ops
    # can filter the queue per subsystem.
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    # Free-form short reason key (e.g. ``refund_provider_error``).
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    # Best-effort target identity; nullable because not every failure is
    # tied to a single domain object (e.g. broadcast notifications).
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    payload: Mapped[dict | None] = mapped_column(_JSON_TYPE, nullable=True)
    status: Mapped[DeadLetterStatus] = mapped_column(
        Enum(DeadLetterStatus, name="dead_letter_status"),
        default=DeadLetterStatus.pending,
        nullable=False,
    )
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
