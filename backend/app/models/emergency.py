"""[F-03] 紧急呼叫相关模型（ADR-0029 加密改造后版本）。

- ``EmergencyContact``: 患者预设的紧急联系人。
  * 手机号字段从 ``phone: str`` → ``phone_encrypted: bytes`` (AES-256-GCM)
  * 新增 ``phone_hash: str(64)`` 用于按号查询不暴露明文（HMAC-SHA256）
  * 新增 ``expires_at`` 列：cron 90d grace 删除（用户主动删除立即硬删）
- ``EmergencyEvent``: 患者触发的紧急事件审计记录。
  * ``contact_called`` 也存密文（沿用 phone_encrypted 字段名以统一）
  * 新增 ``expires_at`` 列：180d 自动清理（cron）
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # ADR-0029: 手机号 AES-256-GCM 密文（base64 字节，由 app.core.pii.encrypt_phone 产生）
    phone_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    # ADR-0029: HMAC-SHA256 hash，64 char hex；用于不暴露明文做按号查询/去重
    phone_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    relationship: Mapped[str] = mapped_column(String(20), nullable=False)
    # ADR-0029: cron 90d grace 删除时间；用户主动删除立即硬删
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
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

    @property
    def phone(self) -> str:
        """明文访问接口。调用时才解密，仅用于 API 序列化 / 业务代码。

            警告：**请勿在日志里直接打印本属性**，请走 mask_phone。
            """
        from app.core.pii import decrypt_phone

        if not self.phone_encrypted:
            return ""
        return decrypt_phone(self.phone_encrypted)


class EmergencyEvent(Base):
    __tablename__ = "emergency_events"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=True,
        index=True,
    )
    # ADR-0029: 被叫号码加密落库（密文 / hash）
    contact_called_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    contact_called_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    # 'contact' | 'hotline'
    contact_type: Mapped[str] = mapped_column(String(20), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    # ADR-0029: 180d 自动清理时间；cron 任务按此列硬删
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    @property
    def contact_called(self) -> str:
        """明文访问接口（API / 业务层）；日志请走 mask_phone。"""
        from app.core.pii import decrypt_phone

        if not self.contact_called_encrypted:
            return ""
        return decrypt_phone(self.contact_called_encrypted)
