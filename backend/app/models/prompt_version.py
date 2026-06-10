"""PromptVersion model (ADR-0048 §5 / S3 prep package generation).

Records the exact prompt text + git commit used to generate AI prep
packages. This gives us a DB-level audit trail independent of source
control history and lets future generation jobs reference a stable
``prompt_version_id`` from ``preparation_packages``.

S3-DEV-002-PROMPT-VERSIONING (ADR-0048 §5.2) — schema extended:

  - ``axis``         BudgetAxis enum value (``s3_prep`` / ``s2_summary`` / ...)
  - ``is_active``    single-truth active flag (one per axis enforced by
                     partial unique index ``ix_prompt_versions_active_per_axis``)
  - ``activated_at`` observability for activation history (NULL until flipped)
  - ``max_tokens``   model max-output cap (NULL = no cap)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("axis", "version", name="uq_prompt_versions_axis_version"),
        # Partial unique index mirrors migration 7a8e1c2d4f60: at most
        # one active prompt per axis. Declared on the model so
        # ``Base.metadata.create_all`` (used by unit-test fixtures)
        # gets the same invariant as production DB migrations.
        Index(
            "ix_prompt_versions_active_per_axis",
            "axis",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Axis: matches BudgetAxis enum value (``s3_prep`` / ``s2_summary``).
    # See app.services.ai_budget_guard.BudgetAxis.  Stored as plain string to
    # avoid coupling to enum migration cost.
    axis: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="s3_prep",
    )
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    git_commit_hash: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    temperature: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    max_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
