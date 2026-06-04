"""Forward lifecycle transitions: create, accept, start (and request/confirm), complete."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.core import error_codes
from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.family_member import FamilyMember
from app.models.order import Order, OrderStatus, ServiceType
from app.models.service_package import ServicePackage
from app.models.user import User, UserRole
from app.repositories.family_member import FamilyMemberRepository
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

        # S2-REQ-003-P3 / ADR-0043 §3: 事务内 SELECT FOR UPDATE 锁档位, 避免 admin 改价 race
        # 档位 code == ServiceType.value (弱外键), 取名称+价格写快照
        pkg_stmt = (
            select(ServicePackage)
            .where(
                ServicePackage.code == service_type.value,
                ServicePackage.is_active.is_(True),
            )
            .with_for_update()
        )
        pkg_result = await self.session.execute(pkg_stmt)
        pkg = pkg_result.scalar_one_or_none()
        if pkg is None:
            raise BadRequestException(
                f"服务档位 「{service_type.value}」 不存在或已下架",
                error_code=error_codes.SERVICE_PACKAGE_INVALID,
            )
        price = pkg.price
        service_name_snapshot = pkg.name
        service_price_snapshot = pkg.price

        companion_id = None
        companion_name = None
        if data.companion_id:
            profile = await self.companion_repo.get_by_id(data.companion_id)
            if profile is None or profile.verification_status.value != "verified":
                raise BadRequestException("Companion not found or not verified")
            companion_id = profile.user_id
            companion_name = profile.real_name

        # F-05: 代他人下单 — 可选；为空 = 给本人下单。
        # 实际就诊人冗余到订单快照，以免以后家人被软删除后历史订单丢上下文。
        family_member: FamilyMember | None = None
        if data.family_member_id:
            family_repo = FamilyMemberRepository(self.session)
            family_member = await family_repo.get_active_for_user(
                data.family_member_id, user.id
            )
            if family_member is None:
                raise NotFoundException("Family member not found")

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
            service_name_snapshot=service_name_snapshot,
            service_price_snapshot=service_price_snapshot,
            hospital_name=hospital.name,
            companion_name=companion_name,
            patient_name=user.display_name or user.phone,
            family_member_id=family_member.id if family_member else None,
            family_member_name=family_member.name if family_member else None,
            family_member_relation=family_member.relation.value if family_member else None,
            family_member_phone=family_member.phone if family_member else None,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=ORDER_EXPIRY_HOURS),
        )
        order = await self.order_repo.create(order)

        await self._record_history(order.id, None, OrderStatus.created, user.id)

        from app.utils.metrics import order_created_total
        _svc_label = service_type.value if hasattr(service_type, 'value') else service_type
        order_created_total.labels(service_type=_svc_label).inc()

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
        await self._check_recon_block(order)

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
        await self._check_recon_block(order)

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
        await self._check_recon_block(order)

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
        await self._check_recon_block(order)

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
        # S2-DEV-006: enqueue AI digest (idempotent on order_id). The actual
        # DeepSeek call + budget caps run in the scheduler-locked worker
        # (app/cron/ai_summary_enqueue.py) so completion isn't blocked and
        # multi-replica retries don't double-charge.
        try:
            from app.cron.ai_summary_enqueue import enqueue_ai_digest

            await enqueue_ai_digest(self.session, order.id)
        except Exception:  # never block completion on the enqueue
            import logging

            logging.getLogger("app.services.order.lifecycle").warning(
                "enqueue_ai_digest failed for order %s", order.id, exc_info=True
            )
        return order
