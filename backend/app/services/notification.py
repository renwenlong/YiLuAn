import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.models.user import User
from app.repositories.notification import NotificationRepository

SERVICE_TYPE_LABELS = {
    "full_accompany": "全程陪诊",
    "half_accompany": "半程陪诊",
    "errand": "代办跑腿",
}


class NotificationService:
    def __init__(self, session: AsyncSession):
        self.notification_repo = NotificationRepository(session)
        self.session = session

    async def list_notifications(
        self, user: User, *, page: int = 1, page_size: int = 20
    ) -> tuple[list, int]:
        skip = (page - 1) * page_size
        return await self.notification_repo.list_by_user(
            user.id, skip=skip, limit=page_size
        )

    async def count_unread(self, user: User) -> int:
        return await self.notification_repo.count_unread(user.id)

    async def mark_read(self, notification_id: uuid.UUID, user: User) -> bool:
        return await self.notification_repo.mark_as_read(notification_id, user.id)

    async def mark_all_read(self, user: User) -> int:
        return await self.notification_repo.mark_all_read(user.id)

    async def create_notification(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        reference_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            reference_id=reference_id,
        )
        notification = await self.notification_repo.create(notification)

        # Push real-time via WebSocket broker (D-019):
        # - 本地投递 + Redis Pub/Sub 跨副本 fanout
        # - broker 未启动（产生于启动失败 / 测试未走 lifespan）时退化为禁用模式
        from app.ws.pubsub import get_current_broker, WsPubSubBroker

        broker = get_current_broker()
        if broker is None:
            # 降级：构造一个空转 broker（等价于旧实现里的"无连接就不推"）
            broker = WsPubSubBroker(redis_client=None, enabled=False)
            broker._started = True  # type: ignore[attr-defined]

        await broker.push_to_user(
            user_id,
            {
                "type": "notification",
                "data": {
                    "id": str(notification.id),
                    "notification_type": type.value,
                    "title": title,
                    "body": body,
                    "reference_id": reference_id,
                    "is_read": False,
                    "created_at": notification.created_at.isoformat() if notification.created_at else None,
                },
            },
        )

        return notification

    async def notify_order_status_changed(
        self,
        order,
        new_status: str,
        recipient_id: uuid.UUID,
    ) -> Notification:
        status_labels = {
            "accepted": "已接单",
            "in_progress": "服务中",
            "completed": "已完成",
            "cancelled_by_patient": "已取消",
            "cancelled_by_companion": "已取消",
        }
        label = status_labels.get(new_status, new_status)
        return await self.create_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title=f"订单状态更新: {label}",
            body=f"订单 {order.order_number} 状态已变更为 {label}",
            reference_id=str(order.id),
        )

    async def notify_start_service_request(
        self,
        order,
        companion_name: str,
        recipient_id: uuid.UUID,
    ) -> Notification:
        return await self.create_notification(
            user_id=recipient_id,
            type=NotificationType.start_service_request,
            title="陪诊师请求开始服务",
            body=f"陪诊师 {companion_name} 请求开始服务，请确认",
            reference_id=str(order.id),
        )

    async def notify_new_message(
        self,
        order_id: uuid.UUID,
        sender_name: str,
        recipient_id: uuid.UUID,
    ) -> Notification:
        return await self.create_notification(
            user_id=recipient_id,
            type=NotificationType.new_message,
            title="新消息",
            body=f"{sender_name} 给您发了一条消息",
            reference_id=str(order_id),
        )

    async def notify_review_received(
        self,
        companion_id: uuid.UUID,
        patient_name: str,
        order_id: uuid.UUID,
        rating: int,
    ) -> Notification:
        return await self.create_notification(
            user_id=companion_id,
            type=NotificationType.review_received,
            title="收到新评价",
            body=f"{patient_name} 给了您 {rating} 星评价",
            reference_id=str(order_id),
        )

    async def notify_new_order(
        self,
        order,
        companion_id: uuid.UUID,
    ) -> Notification:
        type_label = SERVICE_TYPE_LABELS.get(
            order.service_type.value if hasattr(order.service_type, "value") else order.service_type,
            "陪诊",
        )
        return await self.create_notification(
            user_id=companion_id,
            type=NotificationType.new_order,
            title="🔔 新订单来啦",
            body=f"{order.patient_name}预约了{order.appointment_date} {order.appointment_time}在{order.hospital_name}的{type_label}服务，请尽快查看并接单",
            reference_id=str(order.id),
        )

    async def notify_new_order_broadcast(
        self,
        order,
        companion_ids: Sequence[uuid.UUID],
    ) -> list[Notification]:
        type_label = SERVICE_TYPE_LABELS.get(
            order.service_type.value if hasattr(order.service_type, "value") else order.service_type,
            "陪诊",
        )
        notifications = []
        for cid in companion_ids:
            n = await self.create_notification(
                user_id=cid,
                type=NotificationType.new_order,
                title="🔔 附近有新订单",
                body=f"有患者预约了{order.appointment_date} {order.appointment_time}在{order.hospital_name}的{type_label}服务，快来抢单吧",
                reference_id=str(order.id),
            )
            notifications.append(n)
        return notifications

    async def notify_order_rejected(
        self,
        order,
        recipient_id: uuid.UUID,
    ) -> Notification:
        return await self.create_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title="📋 订单需要重新安排",
            body="陪诊师暂时无法为您服务，建议重新选择陪诊师",
            reference_id=str(order.id),
        )

    async def notify_order_expired(
        self,
        order,
        recipient_id: uuid.UUID,
    ) -> Notification:
        return await self.create_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title="⏰ 订单已自动取消",
            body=f"您的订单因超时未被接单已自动取消，款项将原路退回",
            reference_id=str(order.id),
        )
