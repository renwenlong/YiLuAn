import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("order_id", "payment_type", name="uq_payment_order_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    payment_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # "pay" or "refund"
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False
    )  # pending / success / failed
    trade_no: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )  # WeChat transaction id or mock id
    prepay_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )  # WeChat prepay session id
    refund_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )  # Refund tracking number
    callback_raw: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # Raw callback body for audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
