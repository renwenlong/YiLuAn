import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VerificationStatus(str, enum.Enum):
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class CompanionProfile(Base):
    __tablename__ = "companion_profiles"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), unique=True, nullable=False, index=True
    )
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    id_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    certifications: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_area: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_types: Mapped[str | None] = mapped_column(String(200), nullable=True)
    service_hospitals: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    service_city: Mapped[str | None] = mapped_column(String(50), nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avg_rating: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus), default=VerificationStatus.pending, nullable=False
    )
    # F-01: Companion certification display
    certification_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    certification_no: Mapped[str | None] = mapped_column(String(100), nullable=True)
    certification_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    certified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # S3-DEV-003-PRECHECK-BACKEND c1 — admin verify 通过那一刻 timestamp.
    # Set in app/services/admin_audit.py:approve_companion when
    # verification_status flips pending -> verified. Historical verified
    # rows pre-S3 keep NULL; OrderPrecheckSummaryView surfaces NULL as-is
    # (front-end fallback to certified_at per PRD §F4 文案规范).
    # Distinct from certified_at (cert issuance date from credential
    # authority), see ADR-0046 §3.5 + 魈 14:10Z 拍板.
    verification_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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
