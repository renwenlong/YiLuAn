import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notification import (
    Notification,
    NotificationTargetType,
    NotificationType,
)
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.services.notification_outbox import enqueue_notification_outbox

# S2-REQ-003-P4 / ADR-0043 §3 Phase 4: 去硬编码
# 优先读 Order.service_name_snapshot (P3 写入),无快照时 fallback 本 dict。
# fallback 仅保留历史 order 未回填 snapshot 的缺省显示，不作为运行时业务逻辑。
SERVICE_TYPE_LABELS = {
    "full_accompany": "全程陪诊",
    "half_accompany": "半程陪诊",
    "errand": "代办跑腿",
}


def _service_label_from_order(order) -> str:
    """REQ-003 P4: snapshot 优先, dict fallback 兼容历史 order."""
    snap = getattr(order, "service_name_snapshot", None)
    if snap:
        return snap
    code = (
        order.service_type.value
        if hasattr(order.service_type, "value")
        else order.service_type
    )
    return SERVICE_TYPE_LABELS.get(code, "陪诊")


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

    async def get_for_user(
        self, notification_id: uuid.UUID, user: User
    ) -> Notification | None:
        """[F-02] 取出当前用户名下的单条通知（用于标已读后回 target 信息）。"""
        notification = await self.notification_repo.get_by_id(notification_id)
        if notification is None or notification.user_id != user.id:
            return None
        return notification

    async def create_notification(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        reference_id: str | None = None,
        target_type: NotificationTargetType | None = None,
        target_id: str | None = None,
    ) -> Notification:
        notification = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            reference_id=reference_id,
            target_type=target_type,
            target_id=target_id,
        )
        notification = await self.notification_repo.create(notification)

        # Push real-time via WebSocket broker (D-019):
        # - 本地投递 + Redis Pub/Sub 跨副本 fanout
        # - broker 未启动（产生于启动失败 / 测试未走 lifespan）时退化为禁用模式
        from app.ws.pubsub import WsPubSubBroker, get_current_broker

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
                    "target_type": target_type.value if target_type else None,
                    "target_id": target_id,
                    "is_read": False,
                    "created_at": notification.created_at.isoformat() if notification.created_at else None,  # noqa: E501
                },
            },
        )

        return notification

    async def _dispatch_notification(
        self,
        user_id: uuid.UUID,
        type: NotificationType,
        title: str,
        body: str,
        reference_id: str | None = None,
        target_type: NotificationTargetType | None = None,
        target_id: str | None = None,
    ) -> Notification | None:
        """S3-DEV-OUTBOX-3: 业务通知派发的统一出口 (flag 隔离)。

        ``settings.notification_outbox_enabled`` (ADR-0058 §3.4):

        - **False** (默认) → 走旧同步 ``create_notification`` (落库 + 实时 WS 推送)。
          零变更, 现有行为不变 (AC#1/AC#4)。返回落库的 ``Notification``。
        - **True** → 在调用方业务事务内 ``enqueue_notification_outbox`` 写 outbox 表
          (不同步投递, AC#2)。不阻塞业务响应 (AC#6); 投递由 worker (DEV-2)
          后续调 ``_default_deliver`` → ``create_notification`` 落库 + 推送。
          此时返回 ``None`` (还未投递, 无 ``Notification`` 实体)。

        ⚠ 递归防护: flag 仅拦 ``notify_*`` 业务入口。worker 的 ``_default_deliver``
        直调 ``create_notification`` (绕过本 helper / notify_*), 不走 flag 分支 →
        flag True 下 worker 投递不会再次 enqueue, 无无限递归。

        AC#0 payload schema 契约 (铉死 worker ``_default_deliver`` 反序列化口径)::

            {
                "user_id": "<uuid str>",       # 必填, worker UUID(str(...))
                "type": "<NotificationType value>",  # 必填, worker NotificationType(...)
                "title": "...", "body": "...",
                "reference_id": "...",          # optional
                "target_type": "<value>",       # optional, worker NotificationTargetType(...)
                "target_id": "...",             # optional
            }
        """
        if not settings.notification_outbox_enabled:
            return await self.create_notification(
                user_id=user_id,
                type=type,
                title=title,
                body=body,
                reference_id=reference_id,
                target_type=target_type,
                target_id=target_id,
            )

        # flag True: 写 outbox (业务事务内, 不此处 commit)。payload 严格按 worker
        # _default_deliver 反序列化口径构造 (AC#0)。
        payload = {
            "user_id": str(user_id),
            "type": type.value,
            "title": title,
            "body": body,
            "reference_id": reference_id,
            "target_type": target_type.value if target_type is not None else None,
            "target_id": target_id,
        }
        # event_dedup_key: 稳定唯一键 (DB UNIQUE 防同事件重复 enqueue)。
        # 组合 type + user + 业务实体 id (reference 优先, fallback target)。
        anchor = reference_id or target_id or "-"
        event_dedup_key = f"{type.value}:{user_id}:{anchor}"
        await enqueue_notification_outbox(
            self.session,
            event_dedup_key=event_dedup_key,
            payload=payload,
        )
        # 调用方均 fire-and-forget (无人用返回值)。flag True 路径无 Notification 实体。
        return None

    async def notify_order_status_changed(
        self,
        order,
        new_status: str,
        recipient_id: uuid.UUID,
    ) -> Notification | None:
        # 覆盖所有 OrderStatus，并支持同义的多种文案（如 created：待接单）
        status_labels = {
            "created": "待接单",
            "accepted": "已接单",
            "in_progress": "服务中",
            "completed": "已完成",
            "reviewed": "已评价",
            "cancelled_by_patient": "已取消（用户取消）",
            "cancelled_by_companion": "已取消（陪诊师取消）",
            "rejected_by_companion": "陪诊师已拒单",
            "expired": "订单已超时取消",
        }
        label = status_labels.get(new_status, new_status)
        return await self._dispatch_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title=f"订单状态更新: {label}",
            body=f"订单 {order.order_number} 状态已变更为 {label}",
            reference_id=str(order.id),
            target_type=NotificationTargetType.order,
            target_id=str(order.id),
        )

    async def notify_start_service_request(
        self,
        order,
        companion_name: str,
        recipient_id: uuid.UUID,
    ) -> Notification | None:
        return await self._dispatch_notification(
            user_id=recipient_id,
            type=NotificationType.start_service_request,
            title="陪诊师请求开始服务",
            body=f"陪诊师 {companion_name} 请求开始服务，请确认",
            reference_id=str(order.id),
            target_type=NotificationTargetType.order,
            target_id=str(order.id),
        )

    async def notify_new_message(
        self,
        order_id: uuid.UUID,
        sender_name: str,
        recipient_id: uuid.UUID,
    ) -> Notification | None:
        return await self._dispatch_notification(
            user_id=recipient_id,
            type=NotificationType.new_message,
            title="新消息",
            body=f"{sender_name} 给您发了一条消息",
            reference_id=str(order_id),
            target_type=NotificationTargetType.order,
            target_id=str(order_id),
        )

    async def notify_review_received(
        self,
        companion_id: uuid.UUID,
        patient_name: str,
        order_id: uuid.UUID,
        rating: int,
        review_id: uuid.UUID | None = None,
    ) -> Notification | None:
        # F-02: review 类通知优先指向评价本身；若没有 review_id 则退化指向订单。
        if review_id is not None:
            target_type = NotificationTargetType.review
            target_id = str(review_id)
        else:
            target_type = NotificationTargetType.review
            target_id = str(order_id)
        return await self._dispatch_notification(
            user_id=companion_id,
            type=NotificationType.review_received,
            title="收到新评价",
            body=f"{patient_name} 给了您 {rating} 星评价",
            reference_id=str(order_id),
            target_type=target_type,
            target_id=target_id,
        )

    async def notify_new_order(
        self,
        order,
        companion_id: uuid.UUID,
    ) -> Notification | None:
        type_label = _service_label_from_order(order)
        return await self._dispatch_notification(
            user_id=companion_id,
            type=NotificationType.new_order,
            title="🔔 新订单来啦",
            body=f"{order.patient_name}预约了{order.appointment_date} {order.appointment_time}在{order.hospital_name}的{type_label}服务，请尽快查看并接单",  # noqa: E501
            reference_id=str(order.id),
            target_type=NotificationTargetType.order,
            target_id=str(order.id),
        )

    async def notify_new_order_broadcast(
        self,
        order,
        companion_ids: Sequence[uuid.UUID],
    ) -> list[Notification | None]:
        type_label = _service_label_from_order(order)
        notifications = []
        for cid in companion_ids:
            n = await self._dispatch_notification(
                user_id=cid,
                type=NotificationType.new_order,
                title="🔔 附近有新订单",
                body=f"有患者预约了{order.appointment_date} {order.appointment_time}在{order.hospital_name}的{type_label}服务，快来抢单吧",  # noqa: E501
                reference_id=str(order.id),
                target_type=NotificationTargetType.order,
                target_id=str(order.id),
            )
            notifications.append(n)
        return notifications

    async def notify_order_rejected(
        self,
        order,
        recipient_id: uuid.UUID,
    ) -> Notification | None:
        return await self._dispatch_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title="📋 订单需要重新安排",
            body="陪诊师暂时无法为您服务，建议重新选择陪诊师",
            reference_id=str(order.id),
            target_type=NotificationTargetType.order,
            target_id=str(order.id),
        )

    async def notify_order_expired(
        self,
        order,
        recipient_id: uuid.UUID,
    ) -> Notification | None:
        return await self._dispatch_notification(
            user_id=recipient_id,
            type=NotificationType.order_status_changed,
            title="⏰ 订单已自动取消",
            body="您的订单因超时未被接单已自动取消，款项将原路退回",
            reference_id=str(order.id),
            target_type=NotificationTargetType.order,
            target_id=str(order.id),
        )

    async def notify_companion_audit_result(
        self,
        companion_user_id: uuid.UUID,
        companion_profile_id: uuid.UUID,
        approved: bool,
        reason: str | None = None,
    ) -> Notification | None:
        """[F-02] 陪诊师资料审核通过 / 驳回 — 深链跳转到陪诊师档案页。"""
        if approved:
            title = "✅ 陪诊师资料已通过"
            body = "您的陪诊师资料已审核通过，可以接单啦"
        else:
            title = "❌ 陪诊师资料未通过"
            body = f"驳回原因: {reason}" if reason else "您的陪诊师资料未通过审核，请前往修改"
        return await self._dispatch_notification(
            user_id=companion_user_id,
            type=NotificationType.system,
            title=title,
            body=body,
            reference_id=str(companion_profile_id),
            target_type=NotificationTargetType.companion,
            target_id=str(companion_profile_id),
        )
