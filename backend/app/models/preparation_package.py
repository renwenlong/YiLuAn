"""PreparationPackage model (ADR-0048 §7.1).

S3 structured AI prep package. Do not confuse this with S2 ``ai_digests``:

- ``ai_digests`` = family-facing single text summary (S2)
- ``preparation_packages`` = structured 4-block prep package (S3)

The ABAC service layer exposes different column projections from this
same row to user / companion / admin views. In particular, companion
views must never expose ``pre_visit_notes`` or ``possible_questions``.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

_JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")


class PrepStatus(str, enum.Enum):
    pending = "pending"
    generating = "generating"
    active = "active"
    active_fallback_template = "active_fallback_template"
    generation_failed = "generation_failed"


class PreparationPackage(Base):
    __tablename__ = "preparation_packages"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_preparation_packages_order_id"),
        Index("ix_preparation_packages_status_created_at", "status", "created_at"),
        Index("ix_preparation_packages_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[PrepStatus] = mapped_column(
        Enum(
            PrepStatus,
            name="prep_status",
            values_callable=lambda enum_cls: [e.value for e in enum_cls],
        ),
        nullable=False,
        default=PrepStatus.pending,
        server_default=PrepStatus.pending.value,
    )

    # Structured content blocks (JSONB on Postgres, JSON on SQLite tests).
    carry_items: Mapped[list[str] | None] = mapped_column(_JSON_TYPE, nullable=True)
    pre_visit_notes: Mapped[dict | list | str | None] = mapped_column(_JSON_TYPE, nullable=True)
    possible_questions: Mapped[list[str] | None] = mapped_column(_JSON_TYPE, nullable=True)
    companion_focus_points: Mapped[list[str] | None] = mapped_column(
        _JSON_TYPE, nullable=True
    )

    # Generation / ops metadata.
    prompt_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("prompt_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_cost_yuan: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    actual_cost_yuan: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    generation_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # User interaction state.
    user_checked_items: Mapped[list[str] | None] = mapped_column(_JSON_TYPE, nullable=True)

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
