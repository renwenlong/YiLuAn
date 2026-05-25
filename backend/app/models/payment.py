import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Numeric, String, Text, UniqueConstraint, Uuid
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
    # ADR-0030: 金额使用 Decimal/Numeric(10,2)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
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
    # D-058 F2: JSON-encoded sign_params cache so retries of pay_order on a
    # ``pending`` payment can return the **same** signing payload without
    # re-hitting the PSP. Populated on first successful create_prepay.
    sign_params_cache: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
