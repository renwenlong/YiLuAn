"""D-058: HTTP ``Idempotency-Key`` header replay table.

One row per (user_id, endpoint, key). The unique constraint is the
idempotency gate: if a client retries the same write with the same key,
we replay the cached response instead of re-running the handler.

Scope (intentionally narrow for the first iteration):
  * `POST /api/v1/orders` — see ``app/api/v1/orders.py::create_order``.

TTL: 24h. Cleanup is tracked separately (out of scope for this PR; the
column ``expires_at`` exists so a future cron / TD-OPS task can prune).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


# Standard TTL for replay rows. Aligned with industry norm (Stripe = 24h).
IDEMPOTENCY_KEY_TTL = timedelta(hours=24)


def _default_expires_at() -> datetime:
    return datetime.now(timezone.utc) + IDEMPOTENCY_KEY_TTL


class IdempotencyKey(Base):
    """Cached response for a deduplicated client write."""

    __tablename__ = "idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "endpoint",
            "key",
            name="uq_idempotency_user_endpoint_key",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    # e.g. ``POST /api/v1/orders``. Bounded to keep the index narrow.
    endpoint: Mapped[str] = mapped_column(String(64), nullable=False)
    # Client-supplied key. Cap at 128 to keep the (user_id, endpoint, key)
    # BTREE within a single page in PG.
    key: Mapped[str] = mapped_column(String(128), nullable=False)

    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON-serialised response body. Text so SQLite + PG both work without
    # JSONB-specific syntax.
    response_body: Mapped[str] = mapped_column(Text, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_default_expires_at,
        nullable=False,
        index=True,
    )
