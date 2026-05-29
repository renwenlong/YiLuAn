"""AIDigest model (PRD-001 v1.2 §4, S2-DEV-005 上游).

Per-order AI summary cached row. Generation is driven by the W20-D2
AI digest job (S2-DEV-005) which calls DeepSeek with the order's
event timeline and produces a short family-facing summary.

Budget controls (single-order ¥0.05 / daily ¥50 cap) live in the job
itself; this model only stores the *result* + the metadata needed by
audits and the rollback dashboard:

- ``status`` = pending / ok / degraded / failed
  * pending  — job enqueued, not yet finished
  * ok       — generated and post-check passed
  * degraded — fell back to template (post-check hit / provider failed /
               daily budget exhausted) — F2 灰度回滚阈值之一计入这里
  * failed   — terminal failure, no content surfaced
- ``cost_yuan`` — Decimal-as-Numeric, what we actually paid this run
  (per-order budget cap enforced before insert)
- ``degraded_reason`` — short token, used by the metric label
  (``ai_summary_degraded_total{reason}``).

The summary itself is plain text; PII redaction happens in the job
before insert (PRD §F2 family-side PII rules).
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AIDigestStatus(str, enum.Enum):
    PENDING = "pending"
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class AIDigest(Base):
    """One AIDigest row per order (latest revision wins)."""

    __tablename__ = "ai_digests"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_ai_digests_order_id"),
        Index("ix_ai_digests_status", "status"),
        Index("ix_ai_digests_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[AIDigestStatus] = mapped_column(
        SAEnum(
            AIDigestStatus,
            name="ai_digest_status_enum",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        default=AIDigestStatus.PENDING,
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Cost expressed in CNY (¥) with 4-decimal precision so we can
    # truthfully record fractional fen per request.
    cost_yuan: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False, default=Decimal("0.0000")
    )
    degraded_reason: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
