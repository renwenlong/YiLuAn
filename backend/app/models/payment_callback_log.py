"""
Payment callback idempotency log.

Every accepted payment-provider notification is recorded here keyed by
``(provider, transaction_id)``. The unique constraint guarantees that a
duplicate notification (the providers retry aggressively) is detected
**before** any business mutation runs. The endpoint can then short-circuit
with a SUCCESS response without re-applying state changes.

Why a separate table (rather than reusing ``payments.trade_no``)?
-----------------------------------------------------------------
* ``payments.trade_no`` is updated as orders progress, can be NULL during
  prepay, and is shared between pay/refund records — not a stable
  idempotency key.
* We want to log **every** received callback (including ones for which we
  cannot yet locate a Payment row), for audit and retry-debugging.
* Refund callbacks have a separate identifier (``out_refund_no``) which
  must also be deduplicated independently.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PaymentCallbackLog(Base):
    """One row per accepted provider notification.

    Notes
    -----
    * ``transaction_id`` is the provider-side identifier (WeChat
      ``transaction_id`` for pay, ``out_refund_no`` or ``refund_id`` for
      refund). For mock provider tests we use ``out_trade_no`` which is
      sufficient because mock callbacks are dev-only.
    * The unique constraint ``uq_payment_callback_provider_txn`` is the
      idempotency key. Inserts that violate it indicate a duplicate
      delivery — callers must catch ``IntegrityError`` and respond
      with success.
    """

    __tablename__ = "payment_callback_log"
    __table_args__ = (
        UniqueConstraint(
            "provider",
            "transaction_id",
            name="uq_payment_callback_provider_txn",
        ),
        Index(
            "ix_payment_callback_created_at",
            "created_at",
        ),
        Index(
            "ix_payment_callback_log_expires_at",
            "expires_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "mock" | "wechat"
    transaction_id: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    callback_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pay"
    )  # "pay" | "refund"
    out_trade_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="processed"
    )  # "processed" | "ignored" | "rejected"
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # D-027: TTL marker. Application layer fills ``now() + 90d`` on
    # insert. Historical rows (pre-A21-02 migration) remain NULL and
    # are handled by the cleanup job (TD-OPS-02) under a fallback
    # policy keyed off ``created_at``.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
