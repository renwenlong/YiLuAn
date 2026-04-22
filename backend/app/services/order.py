import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core import error_codes
from app.exceptions import BadRequestException, ForbiddenException, NotFoundException, NotExpirableOrderError
from app.models.order import (
    ORDER_TRANSITIONS,
    Order,
    OrderStatus,
    ServiceType,
    SERVICE_PRICES,
)
from app.models.order_status_history import OrderStatusHistory
from app.models.payment import Payment
from app.models.user import User, UserRole
from app.models.chat_message import ChatMessage, MessageType
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.hospital import HospitalRepository
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository, OrderStatusHistoryRepository
from app.repositories.companion_profile import CompanionProfileRepository
from app.schemas.order import CreateOrderRequest
from app.services.notification import NotificationService
from app.services.payment_service import PaymentService, PrepayResult

# Default: orders expire 4 hours after creation
ORDER_EXPIRY_HOURS = 4


def generate_order_number() -> str:
    ts = int(time.time() * 1000) % 10_000_000_000
    rand = uuid.uuid4().hex[:6].upper()
    return f"YLA{ts}{rand}"


class OrderService:
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

    async def create_order(
        self, user: User, data: CreateOrderRequest
    ) -> Order:
        # 前置：手机号必须已绑定（兜底，前端也会拦）
        if not user.phone:
            raise BadRequestException(
                "请先绑定手机号后再下单",
                error_code=error_codes.PHONE_REQUIRED,
            )

        # Check if patient has unpaid orders
        has_unpaid = await self.order_repo.has_unpaid_orders(user.id)
        if has_unpaid:
            raise BadRequestException(
                "您有未支付的订单，请先完成支付后再下单",
                error_code=error_codes.ORDER_HAS_UNPAID,
            )

        hospital = await self.hospital_repo.get_by_id(data.hospital_id)
        if hospital is None:
            raise NotFoundException("Hospital not found")

        service_type = ServiceType(data.service_type)
        price = SERVICE_PRICES[service_type]

        companion_id = None
        companion_name = None
        if data.companion_id:
            profile = await self.companion_repo.get_by_id(data.companion_id)
            if profile is None or profile.verification_status.value != "verified":
                raise BadRequestException("Companion not found or not verified")
            companion_id = profile.user_id
            companion_name = profile.real_name

        order = Order(
            order_number=generate_order_number(),
            patient_id=user.id,
            companion_id=companion_id,
            hospital_id=data.hospital_id,
            service_type=service_type,
            status=OrderStatus.created,
            appointment_date=data.appointment_date,
            appointment_time=data.appointment_time,
            description=data.description,
            price=price,
            hospital_name=hospital.name,
            companion_name=companion_name,
            patient_name=user.display_name or user.phone,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ORDER_EXPIRY_HOURS),
        )
        order = await self.order_repo.create(order)

        await self._record_history(order.id, None, OrderStatus.created, user.id)

        from app.utils.metrics import order_created_total
        order_created_total.labels(service_type=service_type.value if hasattr(service_type, 'value') else service_type).inc()

        return order

    async def get_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")
        if user.role == UserRole.patient and order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if (
            user.role == UserRole.companion
            and order.companion_id is not None
            and order.companion_id != user.id
            and order.status != OrderStatus.created
        ):
            raise ForbiddenException("Not your order")
        await self._fill_payment_status(order)
        await self._fill_timeline(order)
        return order

    async def list_orders(
        self,
        user: User,
        *,
        status: str | None = None,
        date: str | None = None,
        city: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[Sequence[Order], int]:
        skip = (page - 1) * page_size

        # Virtual status: "cancelled" maps to both cancellation types
        if status == "cancelled":
            order_status = None
            status_list = [
                OrderStatus.cancelled_by_patient,
                OrderStatus.cancelled_by_companion,
                OrderStatus.rejected_by_companion,
                OrderStatus.expired,
            ]
        # Virtual status: "completed" includes reviewed orders
        elif status == "completed":
            order_status = None
            status_list = [
                OrderStatus.completed,
                OrderStatus.reviewed,
            ]
        # Virtual status: "in_progress" includes accepted orders
        elif status == "in_progress":
            order_status = None
            status_list = [
                OrderStatus.accepted,
                OrderStatus.in_progress,
            ]
        else:
            order_status = OrderStatus(status) if status else None
            status_list = None

        if user.role == UserRole.companion:
            if order_status == OrderStatus.created:
                items, total = await self.order_repo.list_available(skip=skip, limit=page_size, date=date, city=city)
            else:
                items, total = await self.order_repo.list_by_companion(
                    user.id, status=order_status, status_list=status_list,
                    date=date, skip=skip, limit=page_size,
                )
        else:
            items, total = await self.order_repo.list_by_patient(
                user.id, status=order_status, status_list=status_list,
                date=date, skip=skip, limit=page_size,
            )
        for item in items:
            await self._fill_payment_status(item)
        return items, total

    async def accept_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if user.role != UserRole.companion:
            raise ForbiddenException("Only companions can accept orders")
        # 前置：陪诊师必须已绑定手机号
        if not user.phone:
            raise BadRequestException(
                "请先绑定手机号后再接单",
                error_code=error_codes.PHONE_REQUIRED,
            )
        # 前置：陪诊师资质必须已审核通过
        profile = await self.companion_repo.get_by_user_id(user.id)
        if profile is None or profile.verification_status.value != "verified":
            raise BadRequestException(
                "陪诊师资质未审核通过，暂时不能接单",
                error_code=error_codes.VERIFICATION_REQUIRED,
            )
        self._validate_transition(order.status, OrderStatus.accepted)

        update_data = {
            "status": OrderStatus.accepted,
            "companion_id": user.id,
            # phone 已强制绑定，不再 fallback 到 user.phone
            "companion_name": user.display_name or "陪诊师",
        }
        order = await self.order_repo.update(order, update_data)
        await self._record_history(
            order.id, OrderStatus.created, OrderStatus.accepted, user.id
        )
        # Notify patient that order was accepted
        await self.notification_svc.notify_order_status_changed(
            order, OrderStatus.accepted.value, order.patient_id
        )
        return order

    async def start_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")
        # 前置：订单必须已支付才能开始服务
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if not existing_pay or existing_pay.status != "success":
            raise BadRequestException(
                "订单尚未支付，请提醒患者完成支付后再开始服务",
                error_code=error_codes.PAYMENT_REQUIRED,
            )
        self._validate_transition(order.status, OrderStatus.in_progress)

        order = await self.order_repo.update(
            order, {"status": OrderStatus.in_progress}
        )
        await self._record_history(
            order.id, OrderStatus.accepted, OrderStatus.in_progress, user.id
        )
        # Notify patient that service started
        await self.notification_svc.notify_order_status_changed(
            order, OrderStatus.in_progress.value, order.patient_id
        )
        return order

    async def request_start_service(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")
        if order.status != OrderStatus.accepted:
            raise BadRequestException("订单状态不允许请求开始服务")

        companion_name = user.display_name or user.phone or "陪诊师"
        await self.notification_svc.notify_start_service_request(
            order, companion_name, order.patient_id
        )
        await self._fill_payment_status(order)
        await self._fill_timeline(order)
        return order

    async def confirm_start_service(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        # 前置：订单必须已支付才能确认开始服务
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if not existing_pay or existing_pay.status != "success":
            raise BadRequestException(
                "订单尚未支付，请先完成支付",
                error_code=error_codes.PAYMENT_REQUIRED,
            )
        self._validate_transition(order.status, OrderStatus.in_progress)

        order = await self.order_repo.update(
            order, {"status": OrderStatus.in_progress}
        )
        await self._record_history(
            order.id, OrderStatus.accepted, OrderStatus.in_progress, user.id
        )
        # Notify companion that patient confirmed start
        if order.companion_id:
            await self.notification_svc.notify_order_status_changed(
                order, OrderStatus.in_progress.value, order.companion_id
            )
        await self._fill_payment_status(order)
        await self._fill_timeline(order)
        return order

    async def complete_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")
        self._validate_transition(order.status, OrderStatus.completed)

        order = await self.order_repo.update(
            order, {"status": OrderStatus.completed}
        )
        await self._record_history(
            order.id, OrderStatus.in_progress, OrderStatus.completed, user.id
        )
        # Notify patient that service completed
        await self.notification_svc.notify_order_status_changed(
            order, OrderStatus.completed.value, order.patient_id
        )
        return order

    async def cancel_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)

        if user.role == UserRole.patient:
            if order.patient_id != user.id:
                raise ForbiddenException("Not your order")
            new_status = OrderStatus.cancelled_by_patient
        elif user.role == UserRole.companion:
            if order.companion_id != user.id:
                raise ForbiddenException("Not your order")
            new_status = OrderStatus.cancelled_by_companion
        else:
            raise ForbiddenException("Invalid role")

        self._validate_transition(order.status, new_status)

        old_status = order.status
        order = await self.order_repo.update(order, {"status": new_status})
        await self._record_history(order.id, old_status, new_status, user.id)

        # Auto-refund if already paid — staged refund based on old status
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if existing_pay and existing_pay.status == "success":
            if old_status in (OrderStatus.created, OrderStatus.accepted):
                refund_amount = order.price  # 100% refund
            else:
                refund_amount = round(order.price * 0.5, 2)  # 50% refund
            try:
                await self.payment_svc.create_refund(
                    order_id=order_id,
                    user_id=order.patient_id,
                    original_amount=order.price,
                    refund_amount=refund_amount,
                )
            except BadRequestException as e:
                logger.error(
                    "auto_refund_failed",
                    extra={
                        "order_id": str(order_id),
                        "amount": refund_amount,
                        "reason": str(e.detail),
                        "trigger": "cancel_order",
                    },
                )
                raise BadRequestException(
                    f"订单已取消，但退款失败，请联系客服处理: {e.detail}"
                ) from e

        from app.utils.metrics import order_cancelled_total
        _st = order.service_type.value if hasattr(order.service_type, 'value') else order.service_type
        _cb = user.role.value if hasattr(user.role, 'value') else user.role
        order_cancelled_total.labels(service_type=_st, cancelled_by=_cb).inc()

        # Notify the other party about cancellation
        if user.role == UserRole.patient and order.companion_id:
            await self.notification_svc.notify_order_status_changed(
                order, new_status.value, order.companion_id
            )
        elif user.role == UserRole.companion:
            await self.notification_svc.notify_order_status_changed(
                order, new_status.value, order.patient_id
            )
        return order

    async def pay_order(self, order_id: uuid.UUID, user: User) -> PrepayResult:
        order = await self._get_order_for_update_or_404(order_id)
        if order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if order.status in (
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
            OrderStatus.expired,
        ):
            raise BadRequestException("Cannot pay for a cancelled order")

        result = await self.payment_svc.create_prepay(
            order_id=order.id,
            order_number=order.order_number,
            user_id=user.id,
            amount=order.price,
            description=f"医路安陪诊服务-{order.order_number}",
            openid=getattr(user, "wechat_openid", None),
        )

        # Notify companion(s) about the new paid order
        if order.companion_id:
            await self.notification_svc.notify_new_order(order, order.companion_id)
        else:
            # Broadcast to verified companions in the hospital area
            companions = await self.companion_repo.search(
                hospital_id=str(order.hospital_id), limit=50
            )
            companion_ids = [c.user_id for c in companions]
            if companion_ids:
                await self.notification_svc.notify_new_order_broadcast(
                    order, companion_ids
                )

        # Create system chat message so companions see this order in chat list
        system_msg = ChatMessage(
            order_id=order.id,
            sender_id=user.id,
            type=MessageType.system,
            content="您有一个新的陪诊订单，请查看详情并尽快接单",
        )
        await self.chat_repo.create(system_msg)

        return result

    async def refund_order(self, order_id: uuid.UUID, user: User) -> Payment:
        order = await self._get_order_for_update_or_404(order_id)
        if order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if order.status not in (
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
            OrderStatus.expired,
        ):
            raise BadRequestException("Only cancelled orders can be refunded")

        result = await self.payment_svc.create_refund(
            order_id=order_id,
            user_id=user.id,
            original_amount=order.price,
            refund_amount=order.price,
        )
        # Return the Payment record for API response compatibility
        payment = await self.payment_repo.get_by_order_and_type(order_id, "refund")
        if payment is None:
            raise BadRequestException("Refund record not found")
        return payment

    # --- reject & expiry ---

    async def reject_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_for_update_or_404(order_id)
        if user.role != UserRole.companion:
            raise ForbiddenException("Only companions can reject orders")

        if order.status != OrderStatus.created:
            raise BadRequestException("Can only reject orders in created status")

        # For broadcast orders (no companion_id), companion just skips it — no state change
        if order.companion_id is None:
            raise BadRequestException("广播订单无需拒绝，其他陪诊师仍可接单")

        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")

        self._validate_transition(order.status, OrderStatus.rejected_by_companion)

        order = await self.order_repo.update(
            order, {"status": OrderStatus.rejected_by_companion}
        )
        await self._record_history(
            order.id, OrderStatus.created, OrderStatus.rejected_by_companion, user.id
        )

        # Auto-refund if paid
        existing_pay = await self.payment_repo.get_by_order_and_type(order_id, "pay")
        if existing_pay and existing_pay.status == "success":
            try:
                await self.payment_svc.create_refund(
                    order_id=order_id,
                    user_id=order.patient_id,
                    original_amount=order.price,
                    refund_amount=order.price,
                )
            except BadRequestException as e:
                logger.error(
                    "auto_refund_failed",
                    extra={
                        "order_id": str(order_id),
                        "amount": order.price,
                        "reason": str(e.detail),
                        "trigger": "reject_by_companion",
                    },
                )
                # TODO: dead_letter / ops manual compensation
                # Do not block rejection — patient can request manual refund

        # Notify patient
        await self.notification_svc.notify_order_rejected(order, order.patient_id)
        return order

    async def check_expired_orders(self) -> list[Order]:
        """Check for expired orders and cancel them. Returns list of cancelled orders."""
        now = datetime.now(timezone.utc)
        expired_orders = await self.order_repo.list_expired(now)
        cancelled = []
        for order in expired_orders:
            # --- Fix 1: close / guard payment before expiring ---
            existing_pay = await self.payment_repo.get_by_order_and_type(order.id, "pay")
            if existing_pay:
                if existing_pay.status == "success":
                    # User paid just before expiry — do NOT expire
                    raise NotExpirableOrderError(
                        f"订单 {order.order_number} 已支付成功，无法过期"
                    )
                if existing_pay.status == "pending":
                    try:
                        await self.payment_svc.close_pending_payment(order.id)
                    except BadRequestException:
                        # close_order failed — PSP may have already accepted payment
                        raise NotExpirableOrderError(
                            f"订单 {order.order_number} 支付单关闭失败，无法过期"
                        )

            order = await self.order_repo.update(
                order, {"status": OrderStatus.expired}
            )
            await self._record_history(
                order.id, OrderStatus.created, OrderStatus.expired, order.patient_id
            )

            # Notify patient
            await self.notification_svc.notify_order_expired(order, order.patient_id)
            cancelled.append(order)
        return cancelled

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
