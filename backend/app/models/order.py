import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceType(str, enum.Enum):
    full_accompany = "full_accompany"
    half_accompany = "half_accompany"
    errand = "errand"


# ADR-0030: 金额统一使用 Decimal，避免 IEEE 754 浮点误差
SERVICE_PRICES: dict[ServiceType, Decimal] = {
    ServiceType.full_accompany: Decimal("299.00"),
    ServiceType.half_accompany: Decimal("199.00"),
    ServiceType.errand: Decimal("149.00"),
}


class OrderStatus(str, enum.Enum):
    created = "created"
    accepted = "accepted"
    in_progress = "in_progress"
    completed = "completed"
    reviewed = "reviewed"
    cancelled_by_patient = "cancelled_by_patient"
    cancelled_by_companion = "cancelled_by_companion"
    rejected_by_companion = "rejected_by_companion"
    expired = "expired"


# Valid state transitions: current_status -> set of allowed next statuses
ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.created: {
        OrderStatus.accepted,
        OrderStatus.cancelled_by_patient,
        OrderStatus.rejected_by_companion,
        OrderStatus.expired,
    },
    OrderStatus.accepted: {
        OrderStatus.in_progress,
        OrderStatus.cancelled_by_patient,
        OrderStatus.cancelled_by_companion,
    },
    OrderStatus.in_progress: {
        OrderStatus.completed,
        OrderStatus.cancelled_by_patient,
        OrderStatus.cancelled_by_companion,
    },
    OrderStatus.completed: {
        OrderStatus.reviewed,
    },
    OrderStatus.reviewed: set(),
    OrderStatus.cancelled_by_patient: set(),
    OrderStatus.cancelled_by_companion: set(),
    OrderStatus.rejected_by_companion: set(),
    OrderStatus.expired: set(),
}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    order_number: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    companion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    hospital_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False
    )
    service_type: Mapped[ServiceType] = mapped_column(
        Enum(ServiceType), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), default=OrderStatus.created, nullable=False, index=True
    )
    appointment_date: Mapped[str] = mapped_column(String(10), nullable=False)
    appointment_time: Mapped[str] = mapped_column(String(5), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    hospital_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    companion_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
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
