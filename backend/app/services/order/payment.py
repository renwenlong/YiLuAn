"""Payment-related operations: pay_order (prepay) and refund_order (full refund)."""
from __future__ import annotations

import uuid

from app.exceptions import BadRequestException, ForbiddenException
from app.models.chat_message import ChatMessage, MessageType
from app.models.order import OrderStatus
from app.models.payment import Payment
from app.models.user import User
from app.services.payment_service import PrepayResult

from ._base import _OrderServiceBase


class _OrderPaymentMixin(_OrderServiceBase):
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
