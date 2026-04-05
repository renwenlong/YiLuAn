import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Float, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ServiceType(str, enum.Enum):
    full_accompany = "full_accompany"
    half_accompany = "half_accompany"
    errand = "errand"


SERVICE_PRICES: dict[ServiceType, float] = {
    ServiceType.full_accompany: 299.0,
    ServiceType.half_accompany: 199.0,
    ServiceType.errand: 149.0,
}


class OrderStatus(str, enum.Enum):
    created = "created"
    accepted = "accepted"
    in_progress = "in_progress"
    completed = "completed"
    reviewed = "reviewed"
    cancelled_by_patient = "cancelled_by_patient"
    cancelled_by_companion = "cancelled_by_companion"


# Valid state transitions: current_status -> set of allowed next statuses
ORDER_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.created: {
        OrderStatus.accepted,
        OrderStatus.cancelled_by_patient,
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
    price: Mapped[float] = mapped_column(Float, nullable=False)
    hospital_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    companion_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
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
