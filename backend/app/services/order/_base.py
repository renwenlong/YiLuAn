"""Shared base for OrderService mixins.

SP-01 split: this module owns the `__init__` wiring, all module-level
constants/helpers, and the small private helpers that every mixin reuses.

Each domain mixin (lifecycle / cancel / payment / query / expiry) inherits
from `_OrderServiceBase` so they share repos, services, and helpers.
The composed `OrderService` lives in `app/services/order/__init__.py`.
"""
from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("app.services.order")

from app.exceptions import BadRequestException, NotFoundException
from app.models.order import ORDER_TRANSITIONS, Order, OrderStatus
from app.models.order_status_history import OrderStatusHistory
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.hospital import HospitalRepository
from app.repositories.order import OrderRepository
from app.repositories.payment import OrderStatusHistoryRepository, PaymentRepository
from app.services.notification import NotificationService
from app.services.payment_service import PaymentService

# Default: orders expire 4 hours after creation
ORDER_EXPIRY_HOURS = 4


def generate_order_number() -> str:
    ts = int(time.time() * 1000) % 10_000_000_000
    rand = uuid.uuid4().hex[:6].upper()
    return f"YLA{ts}{rand}"


class _OrderServiceBase:
    """Shared state + private helpers for all OrderService mixins."""

    def __init__(self, session: AsyncSession):
        self.order_repo = OrderRepository(session)
        self.hospital_repo = HospitalRepository(session)
        self.payment_repo = PaymentRepository(session)
        self.history_repo = OrderStatusHistoryRepository(session)
        self.companion_repo = CompanionProfileRepository(session)
        self.notification_svc = NotificationService(session)
        self.payment_svc = PaymentService(session)
        self.chat_repo = ChatMessageRepository(session)
        self.session = session

    @property
    def logger(self) -> logging.Logger:
        """Resolve the package-level logger lazily.

        Mixins call ``self.logger.<level>(...)`` instead of the legacy
        ``sys.modules["app.services.order"].logger`` indirection, but
        tests still patch ``app.services.order.logger``— so we re-read
        the package attr on every access. The tiny dict lookup cost is
        irrelevant compared to the I/O around any log call.
        """
        from app.services import order as _pkg

        return _pkg.logger

    # --- helpers ---

    async def _get_order_or_404(self, order_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")
        return order

    async def _get_order_for_update_or_404(self, order_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_by_id_for_update(order_id)
        if order is None:
            raise NotFoundException("Order not found")
        return order

    def _validate_transition(
        self, current: OrderStatus, target: OrderStatus
    ) -> None:
        allowed = ORDER_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise BadRequestException(
                f"Cannot transition from {current.value} to {target.value}"
            )

    async def _record_history(
        self,
        order_id: uuid.UUID,
        from_status: OrderStatus | None,
        to_status: OrderStatus,
        changed_by: uuid.UUID,
    ) -> None:
        record = OrderStatusHistory(
            order_id=order_id,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            changed_by=changed_by,
        )
        await self.history_repo.create(record)

    async def _fill_payment_status(self, order: Order) -> None:
        payments = await self.payment_repo.list_by_order_id(order.id)
        if any(p.payment_type == "refund" for p in payments):
            order.payment_status = "refunded"
        elif any(p.payment_type == "pay" for p in payments):
            order.payment_status = "paid"
        else:
            order.payment_status = "unpaid"

    STATUS_LABELS = {
        "created": "订单已创建",
        "accepted": "陪诊师已接单",
        "in_progress": "服务进行中",
        "completed": "服务已完成",
        "reviewed": "已评价",
        "cancelled_by_patient": "患者已取消",
        "cancelled_by_companion": "陪诊师已取消",
        "rejected_by_companion": "陪诊师已拒单",
        "expired": "订单已过期",
    }

    # The standard progression used to build a synthetic timeline
    STATUS_PROGRESSION = [
        OrderStatus.created,
        OrderStatus.accepted,
        OrderStatus.in_progress,
        OrderStatus.completed,
        OrderStatus.reviewed,
    ]

    async def _fill_timeline(self, order: Order) -> None:
        history = await self.history_repo.list_by_order_id(order.id)
        if history:
            timeline = []
            for h in history:
                label = self.STATUS_LABELS.get(h.to_status, h.to_status)
                ts = h.created_at.strftime("%Y-%m-%d %H:%M") if h.created_at else ""
                timeline.append({"title": label, "time": ts})
            order.timeline = timeline
            order.timeline_index = len(timeline) - 1 if timeline else -1
            return

        # No history records (e.g. seed data) — build synthetic timeline
        current = order.status
        is_cancelled = current in (
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
            OrderStatus.expired,
        )

        timeline = []
        active_index = 0
        for s in self.STATUS_PROGRESSION:
            label = self.STATUS_LABELS.get(s.value, s.value)
            if s == OrderStatus.created:
                ts = order.created_at.strftime("%Y-%m-%d %H:%M") if order.created_at else ""
            else:
                ts = ""
            timeline.append({"title": label, "time": ts})
            if s.value == current.value:
                active_index = len(timeline) - 1
                break

        if is_cancelled:
            cancel_label = self.STATUS_LABELS.get(current.value, current.value)
            ts = order.updated_at.strftime("%Y-%m-%d %H:%M") if order.updated_at else ""
            timeline.append({"title": cancel_label, "time": ts})
            active_index = len(timeline) - 1

        order.timeline = timeline
        order.timeline_index = active_index
