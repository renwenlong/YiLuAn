import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, String, Text, Uuid
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


class PaymentState(str, enum.Enum):
    """Order-level payment **sub-state** (H2-be / ADR-0035 lite).

    Independent of :class:`OrderStatus`; tracks the money side so the UI
    can show "支付中 / 已付款 / 异常" without coupling to the business
    state machine. ``ORDER_TRANSITIONS`` is intentionally NOT extended.

    解耦契约：**ADR-0041** 支付域与业务域状态机解耦显式化。
    详见 docs/adr/ADR-0041-payment-business-state-machine-decoupling.md。
    任何在 ``ORDER_TRANSITIONS`` 中加入「支付意味」状态（如 ``paid``
    / ``pending_accept`` / ``paying``）的 PR 直接打回 develop。
    """

    none = "none"
    paying = "paying"
    paid = "paid"
    failed = "failed"
    abnormal = "abnormal"


class RefundState(str, enum.Enum):
    """Order-level refund sub-state. ``manual_review`` is set by the
    reconciliation cron when fund-side anomalies are detected."""

    none = "none"
    refunding = "refunding"
    refunded = "refunded"
    failed = "failed"
    manual_review = "manual_review"


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
    payment_state: Mapped[PaymentState] = mapped_column(
        Enum(PaymentState),
        default=PaymentState.none,
        server_default=PaymentState.none.value,
        nullable=False,
        index=True,
    )
    refund_state: Mapped[RefundState] = mapped_column(
        Enum(RefundState),
        default=RefundState.none,
        server_default=RefundState.none.value,
        nullable=False,
        index=True,
    )
    appointment_date: Mapped[str] = mapped_column(String(10), nullable=False)
    appointment_time: Mapped[str] = mapped_column(String(5), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    # S2-REQ-003-P3 / ADR-0043 §3: 价格快照 (来自 service_packages 档位)
    # nullable=True 以兼容历史 orders 行 (migration 回填), 新建订单 create_order 强制写入
    service_name_snapshot: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="下单时 service_packages.name 快照 (P3)",
    )
    service_price_snapshot: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 2), nullable=True,
        comment="下单时 service_packages.price 快照, 支付/退款一律读此字段 (P3)",
    )
    hospital_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    companion_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    patient_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # F-05: 代他人下单 — 软关联 + 冗余快照（家人删除后仍可还原显示）
    family_member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, index=True
    )
    family_member_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    family_member_relation: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    family_member_phone: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # S3-DEV-001-CONTRACT-DOMAIN (ADR-0047 §3.3): nullable FK back-pointer from
    # order to its generated contract row. Nullable since contract is not
    # required for order to be considered valid (PRD-003 §AC-5).
    # 不回填历史 orders 行; 新订单 ContractService 写入。
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "service_contracts.id",
            use_alter=True,
            name="fk_orders_contract_id",
        ),
        nullable=True,
        comment="一单一合同 nullable (PRD-003 §AC-5); use_alter 防循环 FK",
    )

    # ADR-0047 §3.3: 一单一保单 nullable FK — 保险不影响订单成立 (PRD-003 §AC-5)
    # 不回填历史 orders 行; S3 启动后新订单 InsuranceService 写入。
    insurance_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "service_insurance_records.id",
            use_alter=True,
        ),
        nullable=True,
        comment="一单一保单, nullable 因保险不影响订单成立 (PRD-003 AC-5)",
    )
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
