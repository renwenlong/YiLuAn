import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("orders.id"), nullable=False, unique=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    companion_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    # F-04 multi-dimension ratings (1~5). Nullable for legacy rows that
    # haven't been backfilled (the alembic migration backfills with the
    # legacy `rating` value); ReviewService always writes all 4 on new rows.
    punctuality_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    professionalism_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    communication_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attitude_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
