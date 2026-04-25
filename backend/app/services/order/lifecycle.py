"""Forward lifecycle transitions: create, accept, start (and request/confirm), complete."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.core import error_codes
from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.order import Order, OrderStatus, SERVICE_PRICES, ServiceType
from app.models.user import User, UserRole
from app.schemas.order import CreateOrderRequest

from ._base import ORDER_EXPIRY_HOURS, _OrderServiceBase, generate_order_number


class _OrderLifecycleMixin(_OrderServiceBase):
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
