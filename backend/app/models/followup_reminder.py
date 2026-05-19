"""F-07: follow-up reminder (复诊提醒).

模型存一条待发送/已发送/失败的微信订阅消息记录。以订单为载体：
只有 ``completed`` / ``reviewed`` 的订单才允许预约复诊提醒。

状态机：pending → sent / failed。连续失败 ``MAX_ATTEMPTS`` 次后锁定为
``failed`` 不再重试。成功送达记为 ``sent`` 以 ``sent_at`` 为准。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FollowupReminderStatus(str, enum.Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    cancelled = "cancelled"


MAX_ATTEMPTS = 3


class FollowupReminder(Base):
    __tablename__ = "followup_reminders"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), nullable=False, index=True
    )
    remind_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    status: Mapped[FollowupReminderStatus] = mapped_column(
        Enum(FollowupReminderStatus),
        nullable=False,
        default=FollowupReminderStatus.pending,
        server_default=FollowupReminderStatus.pending.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 可选：用户自定义备注（上线后可以拼到模板 thing4 字段）
    note: Mapped[str | None] = mapped_column(String(140), nullable=True)
    # Provider 返回的业务号（微信订阅消息 msgid 等）；stub 为空
    provider_message_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
