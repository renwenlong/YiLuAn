import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NotificationType(str, enum.Enum):
    order_status_changed = "order_status_changed"
    new_message = "new_message"
    new_order = "new_order"
    review_received = "review_received"
    start_service_request = "start_service_request"
    system = "system"


class NotificationTargetType(str, enum.Enum):
    """[F-02] 深链跳转目标类型。

    与 ``NotificationType`` 解耦：``type`` 描述事件类别（业务上面向用户的语义），
    ``target_type`` 描述点击通知后要跳转到哪个领域对象。
    """

    order = "order"
    companion = "companion"
    system = "system"
    payment = "payment"
    review = "review"


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    type: Mapped[NotificationType] = mapped_column(
        Enum(NotificationType), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # [F-02] 深链跳转字段。两个字段都可空——保留对历史数据 / system 类通知的兼容。
    target_type: Mapped[NotificationTargetType | None] = mapped_column(
        Enum(NotificationTargetType, name="notificationtargettype"),
        nullable=True,
    )
    target_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
