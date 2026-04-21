"""SMS 发送审计日志（A21-02b / D-033）。

每次 SMS 发送（OTP / 通知）入口都会写入一行：
1. 调用 provider 之前 INSERT ``status='pending'``
2. provider 返回成功 → UPDATE ``status='success'`` + ``biz_id`` / 响应字段
3. provider 抛错 → UPDATE ``status='failed'`` + 记录错误信息后 **re-raise**

字段设计
--------
* **不含 ``params``**：OTP 明文绝不入库（避免 PII 二次泄漏）。
* **phone 双列**：``phone_masked``（``138****1234``，给人看 / 客服查询）
  + ``phone_hash``（SHA256 hex with salt，给等值检索 / 关联）。
* **无 DB 唯一约束**：OTP 反爆破由业务层 / Redis 限流（commit ce4259e）
  兜底，DB 层只做日志，方便重放/补偿。
* ``expires_at``：与 D-027 一致，应用层填 ``now() + 90d``，TD-OPS-02
  清理 job 统一回收。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SmsSendLog(Base):
    """One row per SMS send attempt (OTP, notification, ...)."""

    __tablename__ = "sms_send_log"
    __table_args__ = (
        Index("ix_sms_send_log_phone_hash", "phone_hash"),
        Index("ix_sms_send_log_biz_id", "biz_id"),
        Index("ix_sms_send_log_created_at", "created_at"),
        Index("ix_sms_send_log_expires_at", "expires_at"),
    )

    # SQLite 不支持 BIGINT autoincrement —— 使用 with_variant 让 SQLite 走
    # 普通 INTEGER PRIMARY KEY（隐式 ROWID 自增），PG/MySQL 走 BIGSERIAL/BIGINT
    # AUTO_INCREMENT。与 migration 文件保持一致。
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    phone_masked: Mapped[str] = mapped_column(String(20), nullable=False)
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    template_code: Mapped[str] = mapped_column(String(64), nullable=False)
    sign_name: Mapped[str | None] = mapped_column(String(32), nullable=True)
    biz_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    response_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    response_msg: Mapped[str | None] = mapped_column(String(512), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_sms_send_log_user_id_users",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # D-027: TTL marker. Application layer fills ``now() + 90d`` on insert.
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"<SmsSendLog id={self.id} provider={self.provider!r} "
            f"phone={self.phone_masked!r} template={self.template_code!r} "
            f"status={self.status!r} biz_id={self.biz_id!r}>"
        )
