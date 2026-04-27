import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.emergency import EmergencyContact, EmergencyEvent
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.repositories.payment import PaymentRepository
from app.repositories.user import UserRepository
from app.schemas.user import UpdateUserRequest
from app.services.payment_service import PaymentService

logger = logging.getLogger(__name__)

# Order statuses that count as "in progress" (cancellable on account deletion)
_ACTIVE_ORDER_STATUSES = [
    OrderStatus.created,
    OrderStatus.accepted,
    OrderStatus.in_progress,
]

# Statuses that require a refund when cancelled during account deletion
_REFUNDABLE_STATUSES = [
    OrderStatus.accepted,
    OrderStatus.in_progress,
]


class UserService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    async def get_user_by_id(self, user_id: UUID) -> User:
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundException("User not found")
        return user

    async def update_user(self, user: User, data: UpdateUserRequest) -> User:
        update_data = data.model_dump(exclude_unset=True)

        if "role" in update_data and update_data["role"] is not None:
            new_role = UserRole(update_data["role"])
            update_data["role"] = new_role
            user.add_role(new_role)
            update_data["roles"] = user.roles

        if not update_data:
            return user

        return await self.user_repo.update(user, update_data)

    async def switch_role(self, user: User, role_str: str) -> User:
        target_role = UserRole(role_str)
        if not user.has_role(target_role):
            raise BadRequestException(f"User does not have role: {role_str}")
        return await self.user_repo.update(user, {"role": target_role})

    async def delete_account(self, user: User) -> None:
        """Soft-delete account: cancel active orders, anonymize PII, set deleted_at.

        ADR-0029 / D-043: 在软删账号之前，**硬删** user 名下所有
        ``emergency_contacts`` 和 ``emergency_events``，不走 90 / 180 天保留期。
        并写入 audit 日志（action="user_self_delete"）。
        """
        if user.is_deleted:
            raise BadRequestException("Account is already deleted")

        # 1) Cancel in-progress orders (as patient or companion)
        await self._cancel_active_orders(user.id)

        # 2) ADR-0029 / D-043: 硬删紧急联系人 + 事件（在匿名化之前）
        contacts_purged, events_purged = await self._purge_emergency_data(user.id)

        # 3) Anonymize PII
        phone_hash = (
            hashlib.sha256(user.phone.encode()).hexdigest()[:16]
            if user.phone
            else None
        )
        update_data = {
            "phone": phone_hash,
            "display_name": "已注销用户",
            "avatar_url": None,
            "wechat_openid": None,
            "wechat_unionid": None,
            "is_active": False,
            "deleted_at": datetime.now(timezone.utc),
        }
        await self.user_repo.update(user, update_data)

        # 4) ADR-0029: 写 audit
        audit = AdminAuditLog(
            target_type="user",
            target_id=user.id,
            action="user_self_delete",
            operator=f"user:{user.id}",
            reason=json.dumps(
                {
                    "emergency_contacts_purged": contacts_purged,
                    "emergency_events_purged": events_purged,
                },
                ensure_ascii=False,
            ),
        )
        self.session.add(audit)
        await self.session.flush()

    async def _purge_emergency_data(self, user_id: UUID) -> tuple[int, int]:
        """硬删 user 名下所有 emergency_contacts + emergency_events，返回 (N, M)。"""
        # 先查个数（为了 audit）
        contacts_count = (
            await self.session.execute(
                select(EmergencyContact).where(EmergencyContact.user_id == user_id)
            )
        ).scalars().all()
        events_count = (
            await self.session.execute(
                select(EmergencyEvent).where(EmergencyEvent.patient_id == user_id)
            )
        ).scalars().all()

        n = len(contacts_count)
        m = len(events_count)

        if n:
            await self.session.execute(
                delete(EmergencyContact).where(EmergencyContact.user_id == user_id)
            )
        if m:
            await self.session.execute(
                delete(EmergencyEvent).where(EmergencyEvent.patient_id == user_id)
            )
        return n, m

    async def _cancel_active_orders(self, user_id: UUID) -> None:
        """Cancel all active orders and trigger refunds per D-009.

        - pending (created) orders → cancel (no refund needed)
        - accepted orders → cancel + 100% refund
        - in_progress orders → cancel + 50% refund
        - completed/reviewed orders → untouched
        """
        stmt = select(Order).where(
            Order.status.in_(_ACTIVE_ORDER_STATUSES),
            (Order.patient_id == user_id) | (Order.companion_id == user_id),
        )
        result = await self.session.execute(stmt)
        orders = result.scalars().all()

        if not orders:
            return

        payment_svc = PaymentService(self.session)
        payment_repo = PaymentRepository(self.session)

        for order in orders:
            old_status = order.status
            order.status = OrderStatus.cancelled_by_patient

            # Trigger refund for accepted/in_progress orders that have been paid
            if old_status in _REFUNDABLE_STATUSES:
                existing_pay = await payment_repo.get_by_order_and_type(
                    order.id, "pay"
                )
                if existing_pay and existing_pay.status == "success":
                    if old_status == OrderStatus.accepted:
                        refund_amount = order.price  # 100% refund
                    else:
                        # ADR-0030: Decimal 半进位
                        refund_amount = (order.price * Decimal("0.5")).quantize(
                            Decimal("0.01"), rounding=ROUND_HALF_UP
                        )
                    try:
                        await payment_svc.create_refund(
                            order_id=order.id,
                            user_id=order.patient_id,
                            original_amount=order.price,
                            refund_amount=refund_amount,
                        )
                    except BadRequestException:
                        logger.warning(
                            "Refund skipped for order %s (already refunded)",
                            order.id,
                        )

        await self.session.flush()
