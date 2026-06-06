"""Service insurance record ORM model (S3-DEV-001-INSURANCE-DOMAIN / ADR-0047 §3.3).

# Domain context

S3 阶段陪诊服务订单生效时附带一份"陪诊责任险"。本表记录每单的保险单:
- vendor 实际接入留下一迭代 — S3 用 PLACEHOLDER_VENDOR 直接 active
- 一单一保单 (UNIQUE order_id)
- 保险**不影响**订单成立 — orders.insurance_id nullable (PRD-003 §AC-5)

# State machine (see ``insurance_state_machine.py``)

```
pending_issue ──→ active
                   │
                   ├──→ expired         (服务完成 + 保障期过)
                   └──→ cancelled       (订单退款 / 取消)

pending_issue ──→ issue_failed         (vendor API 失败 — S3 阶段无真 vendor 永不触发)

any ──→ manually_invalidated           (admin 手动作废,留痕必填)
```

# Compensation cron (ADR-0046 §3.4 同款 5min/30min/2h 三档)

`issue_failed` 状态走 apscheduler cron 补偿:
- T+5min: 1st retry
- T+30min after 1st: 2nd retry
- T+2h after 2nd: 3rd retry
- 3 次全失败 → status 仍 `issue_failed` + admin alert (alertmanager)

S3 阶段因 vendor=PLACEHOLDER 永远成功,cron 实际不会触发补偿路径,
但代码完整实施 — 下迭代切真 vendor 时无需再加 retry 框架。
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InsuranceStatus(str, enum.Enum):
    """Insurance order lifecycle states (ADR-0047 §3.3)."""

    pending_issue = "pending_issue"
    """初始: 等 vendor 出单 (S3 阶段 vendor=PLACEHOLDER, 立即升级 active)."""

    active = "active"
    """vendor 确认出单, 保单生效."""

    expired = "expired"
    """服务完成 + 保障期过, 自然到期."""

    cancelled = "cancelled"
    """订单退款 / 取消 → 保险同步作废 (区别于 manually_invalidated 主动作废)."""

    issue_failed = "issue_failed"
    """vendor API 失败 (S3 阶段无真 vendor 永不触发); 补偿 cron 重试 3 次."""

    manually_invalidated = "manually_invalidated"
    """admin 手动作废, 留痕必填 (invalidation_reason + invalidated_by_admin_id)."""


# PLACEHOLDER vendor name used during S3 phase (no real vendor integration).
# Schema-stable: switching to a real vendor next iter only updates data row,
# never the column type / name.
PLACEHOLDER_VENDOR_NAME = "PLACEHOLDER_VENDOR"


class ServiceInsuranceRecord(Base):
    """Service insurance order record (一单一保单, ADR-0047 §3.3).

    Lifecycle owned by :class:`InsuranceStateMachine`; any direct ORM
    mutation of ``status`` outside the state machine must raise during
    code review (see ``insurance_state_machine`` for transition table).
    """

    __tablename__ = "service_insurance_records"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # 一单一保单 — UNIQUE 在表级别强制 (Alembic CREATE TABLE)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=False,
        unique=True,
        index=True,
        comment="一单一保单, 禁重复出单 (ADR-0047 §3.3)",
    )

    # Vendor 字段 - S3 阶段用 PLACEHOLDER, 下迭代切真 vendor 不改 schema
    product_name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        comment='保险产品名, 如 "陪诊责任险标准版"',
    )
    coverage_amount_cny: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="保额, 分单位整数 (ADR-0030 金额规范, 与 contract amount_cny 一致)",
    )
    vendor_name: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=PLACEHOLDER_VENDOR_NAME,
        server_default=PLACEHOLDER_VENDOR_NAME,
        comment="保险公司; S3 用 PLACEHOLDER_VENDOR (PRD-003 §2.2)",
    )
    vendor_policy_no: Mapped[str | None] = mapped_column(
        String(128),
        nullable=True,
        comment='vendor 保单号 (PRD-003 §3.3 AC-4 允许 PENDING); S3: "PLACEHOLDER-{order_id8}"',
    )

    # State machine 字段
    status: Mapped[InsuranceStatus] = mapped_column(
        Enum(InsuranceStatus, name="insurance_status"),
        nullable=False,
        default=InsuranceStatus.pending_issue,
        server_default=InsuranceStatus.pending_issue.value,
        index=True,
        comment="状态机由 InsuranceStateMachine 维护; 直接 UPDATE 禁",
    )

    # 失败 / 补偿 cron 字段 (issue_failed 状态用)
    retry_count: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
        default=0,
        server_default="0",
        comment="补偿 cron retry 次数 (5min/30min/2h 三档, 上限 3)",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="最近一次失败的 error trace; AC#4",
    )

    # 生命周期时间戳
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="vendor 确认出单时间; status=active 时设",
    )

    # manually_invalidated 留痕 (AC#5: 必填)
    invalidation_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="作废原因; status=manually_invalidated 时**必填** (AC#5)",
    )
    invalidated_by_admin_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("admin_users.id"),
        nullable=True,
        comment="作废人 admin_user_id; status=manually_invalidated 时**必填** (AC#5)",
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="作废时间",
    )

    # 审计字段
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


__all__ = [
    "InsuranceStatus",
    "PLACEHOLDER_VENDOR_NAME",
    "ServiceInsuranceRecord",
]
