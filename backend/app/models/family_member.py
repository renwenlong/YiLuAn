"""F-05: family members (代他人下单).

A *family member* is a non-account person that a user can place orders on
behalf of (typically an elderly parent). The booking user remains the
order owner (patient_id == booking user), but the order is denormalized
with the family member's name / relation / phone so the companion knows
who they are actually accompanying.

Hard rules (D-056):
* `user_id` is indexed; one user may have many members.
* `deleted_at` for soft-delete — historical orders keep their reference.
* No id-card / no shared payment / no inter-member transfer in MVP.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FamilyRelation(str, enum.Enum):
    self_ = "self"  # rarely used; we usually skip the row entirely
    parent = "parent"
    spouse = "spouse"
    child = "child"
    sibling = "sibling"
    grandparent = "grandparent"
    relative = "relative"
    friend = "friend"
    other = "other"


class FamilyGender(str, enum.Enum):
    unknown = "unknown"
    male = "male"
    female = "female"


class FamilyMember(Base):
    __tablename__ = "family_members"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    relation: Mapped[FamilyRelation] = mapped_column(
        Enum(FamilyRelation),
        nullable=False,
        default=FamilyRelation.other,
        server_default=FamilyRelation.other.value,
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    gender: Mapped[FamilyGender] = mapped_column(
        Enum(FamilyGender),
        nullable=False,
        default=FamilyGender.unknown,
        server_default=FamilyGender.unknown.value,
    )
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    medical_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
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
