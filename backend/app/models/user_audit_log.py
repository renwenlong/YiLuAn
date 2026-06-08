"""UserAuditLog model — 用户侧合同/保险审计 (ADR-0047 §3.5)

PIPL/民法典电子合同取证: 用户勾选合同 / 查看合同 / 查看保障条款行为入此表。
admin 操作仍走 admin_audit_logs (物理隔离)。

3 actions:
- contract_acceptance_clicked
- contract_viewed
- insurance_terms_viewed
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserAuditAction(str, enum.Enum):
    """ADR-0047 §3.5: 3 actions 入用户审计表"""

    contract_acceptance_clicked = "contract_acceptance_clicked"
    contract_viewed = "contract_viewed"
    insurance_terms_viewed = "insurance_terms_viewed"


class UserAuditLog(Base):
    """用户侧合同/保险审计 (ADR-0047 §3.5)

    与 AdminAuditLog 物理隔离:
    - admin 操作 → admin_audit_logs
    - user 行为 (勾选合同 / 查看合同 / 查看保障条款) → user_audit_logs

    user_agent + client_ip 必填 (PIPL/民法典电子合同取证):
    - 缺失 IP 写 "0.0.0.0" + metadata 加 missing_ip=True
    - 反代提取真实 IP (X-Forwarded-For / X-Real-IP)
    """

    __tablename__ = "user_audit_logs"
    __table_args__ = (
        Index(
            "idx_user_audit_logs_user_time",
            "user_id",
            text("created_at DESC"),
        ),
        Index(
            "idx_user_audit_logs_order_action",
            "order_id",
            "action",
        ),
        {
            "comment": "用户侧合同/保险审计 (ADR-0047 §3.5, 与 admin_audit_logs 物理隔离)"
        },
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="UUID primary key",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        comment="行为发起用户 (FK users.id, ADR-0047 §3.5)",
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=True,
        comment="关联订单 (可选, 查看保障条款无订单场景为 NULL)",
    )
    action: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="行为类型: contract_acceptance_clicked / contract_viewed / insurance_terms_viewed",
    )
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
        comment="扩展元数据 (template_version / missing_ip / 其他取证信息)",
    )
    user_agent: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="User-Agent 字符串 (PIPL/民法典电子合同取证, 刻晴 #3 补充)",
    )
    client_ip: Mapped[str] = mapped_column(
        String(45),
        nullable=False,
        comment="真实客户端 IP (反代提取, 缺失写 0.0.0.0; 支持 IPv6 故 45 字符)",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="创建时间 (UTC)",
    )
