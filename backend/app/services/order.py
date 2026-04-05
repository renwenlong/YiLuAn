import time
import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
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
from app.repositories.hospital import HospitalRepository
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository, OrderStatusHistoryRepository
from app.repositories.companion_profile import CompanionProfileRepository
from app.schemas.order import CreateOrderRequest
from app.services.notification import NotificationService


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
        self.session = session

    async def create_order(
        self, user: User, data: CreateOrderRequest
    ) -> Order:
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
        )
        order = await self.order_repo.create(order)

        await self._record_history(order.id, None, OrderStatus.created, user.id)
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
            ]
        else:
            order_status = OrderStatus(status) if status else None
            status_list = None

        if user.role == UserRole.companion:
            if order_status == OrderStatus.created:
                return await self.order_repo.list_available(skip=skip, limit=page_size, date=date, city=city)
            return await self.order_repo.list_by_companion(
                user.id, status=order_status, status_list=status_list,
                date=date, skip=skip, limit=page_size,
            )
        return await self.order_repo.list_by_patient(
            user.id, status=order_status, status_list=status_list,
            date=date, skip=skip, limit=page_size,
        )

    async def accept_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_or_404(order_id)
        if user.role != UserRole.companion:
            raise ForbiddenException("Only companions can accept orders")
        self._validate_transition(order.status, OrderStatus.accepted)

        update_data = {
            "status": OrderStatus.accepted,
            "companion_id": user.id,
            "companion_name": user.display_name or user.phone,
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
        order = await self._get_order_or_404(order_id)
        if order.companion_id != user.id:
            raise ForbiddenException("Not your order")
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

    async def complete_order(self, order_id: uuid.UUID, user: User) -> Order:
        order = await self._get_order_or_404(order_id)
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
        order = await self._get_order_or_404(order_id)

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

        order = await self.order_repo.update(order, {"status": new_status})
        await self._record_history(order.id, order.status, new_status, user.id)
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

    async def pay_order(self, order_id: uuid.UUID, user: User) -> Payment:
        order = await self._get_order_or_404(order_id)
        if order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if order.status in (
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
        ):
            raise BadRequestException("Cannot pay for a cancelled order")

        existing = await self.payment_repo.get_by_order_id(order_id)
        if existing and existing.payment_type == "pay":
            raise BadRequestException("Order already paid")

        payment = Payment(
            order_id=order_id,
            user_id=user.id,
            amount=order.price,
            payment_type="pay",
            status="success",
        )
        return await self.payment_repo.create(payment)

    async def refund_order(self, order_id: uuid.UUID, user: User) -> Payment:
        order = await self._get_order_or_404(order_id)
        if order.patient_id != user.id:
            raise ForbiddenException("Not your order")
        if order.status not in (
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
        ):
            raise BadRequestException("Only cancelled orders can be refunded")

        existing_pay = await self.payment_repo.get_by_order_id(order_id)
        if not existing_pay or existing_pay.payment_type != "pay":
            raise BadRequestException("Order has no payment to refund")

        refund = Payment(
            order_id=order_id,
            user_id=user.id,
            amount=order.price,
            payment_type="refund",
            status="success",
        )
        return await self.payment_repo.create(refund)

    # --- helpers ---

    async def _get_order_or_404(self, order_id: uuid.UUID) -> Order:
        order = await self.order_repo.get_by_id(order_id)
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
