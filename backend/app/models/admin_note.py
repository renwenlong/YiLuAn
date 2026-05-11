"""Admin note model — internal CS / ops notes attached to a target entity.

Targets are addressed via the same ``(target_type, target_id)`` pair we use
for ``AdminAuditLog`` so a single note table can serve order ticket comments,
user CS notes, companion flags, etc. without per-entity bespoke tables.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminNote(Base):
    __tablename__ = "admin_notes"
    __table_args__ = (
        Index("ix_admin_notes_target", "target_type", "target_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target_type: Mapped[str] = mapped_column(String(50), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    operator: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
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
