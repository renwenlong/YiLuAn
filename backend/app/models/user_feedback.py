"""User feedback ORM model (S3-DEV-004-FEEDBACK-DOMAIN / ADR-0049).

# Domain context

PRD-004 v0.3 用户/家属反馈采集通路. 反馈作为第 7 个业务状态机
(orders / contract / insurance / preparation_package / wallet / share / **user_feedback**),
按 ADR-0049 §2.1 与订单状态机解耦, 仅 nullable FK 关联 Order / Companion / FunctionModule.

# 范围 (本 task)

- ``user_feedbacks`` 表 + 4 个 ENUM
- ``UserFeedbackStateMachine`` 独立类 (status 流转, 不污染 OrderStateMachine)
- 单测覆盖状态迁移 + 三外键 nullable

# 不在范围

- ``feedback_attachments`` 表 → S3-DEV-004-FEEDBACK-STORAGE
- endpoint / service / 限频 / metrics / 告警 → S3-DEV-004-FEEDBACK-API
- AI 摘要 (PRD-004 明确 S3 不做)

# 三大外键 nullable rationale (ADR-0049 §3.1)

- ``order_id`` NULL: 平台级反馈不绑订单 (功能建议 / 隐私担忧 / 平台流程)
- ``companion_id`` NULL: 非对陪诊师反馈 (平台 / 流程 / 服务质量但非具体陪诊师)
- ``feedback_parent_id`` NULL: 首条反馈 (parent IS NULL); 非 NULL = 补充反馈

# 唯一约束 (ADR-0049 §3.2)

partial UNIQUE INDEX:
``(user_id, order_id, category) WHERE feedback_parent_id IS NULL AND order_id IS NOT NULL``

- 防"同用户对同订单同类别"重复首条反馈
- 补充反馈不受限 (feedback_parent_id IS NOT NULL)
- 平台级反馈不受限 (order_id IS NULL)
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Final

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# ---------------------------------------------------------------------------
# ENUMs (ADR-0049 §3.1)
# ---------------------------------------------------------------------------


class FeedbackStatus(str, enum.Enum):
    """Feedback lifecycle states (ADR-0049 §4.1, 5 states ground truth)."""

    pending = "pending"
    """初始: 用户/家属/客服代录已提交, admin 未触达."""

    in_review = "in_review"
    """admin 处理中 (已 start_review). 可生成 sanitized_summary 给陪诊师可见."""

    resolved = "resolved"
    """admin 已处理完成. 等用户 accept / 超时 → closed."""

    closed = "closed"
    """user 接受 / 30d 超时关闭. 30d 内 user 仍可 append → 转 in_review."""

    rejected = "rejected"
    """admin 判定无效/重复/恶意. user 仍可 append → 转 in_review."""


class FeedbackSeverity(str, enum.Enum):
    """Feedback severity (ADR-0049 §3.1)."""

    normal = "normal"
    important = "important"
    urgent = "urgent"
    """触发 alertmanager UrgentFeedbackSubmitted alert (S3-DEV-004-FEEDBACK-API task 跟)."""


class FeedbackSource(str, enum.Enum):
    """Feedback submission source (ADR-0049 §3.1)."""

    user = "user"
    """用户/家属 self-service 通过 user endpoint 提交."""

    customer_service = "customer_service"
    """客服在 admin-v2 后台代录."""

    phone = "phone"
    """电话客服代录."""

    offline = "offline"
    """线下渠道 (面访 / 书面) 录入."""


class FeedbackFunctionModule(str, enum.Enum):
    """Function module domain (ADR-0049 §3.1).

    覆盖 8 个功能模块. ``other`` 兜底未来扩展, 防 ENUM 漂移频繁 migration.
    """

    insurance = "insurance"
    contract = "contract"
    ai_prep = "ai_prep"
    family_share = "family_share"
    service_package = "service_package"
    service_quality = "service_quality"
    payment = "payment"
    other = "other"


# admin_users.id is BigInteger in PG / Integer in SQLite (see app.models.admin_user)
_ADMIN_ID_TYPE = BigInteger().with_variant(Integer(), "sqlite")


# PostgreSQL JSONB type with SQLite JSON fallback (for default test fixtures).
_JsonbType = JSONB().with_variant(JSON(), "sqlite")


# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class UserFeedback(Base):
    """User/family feedback record (ADR-0049 §3.1).

    Lifecycle owned by :class:`UserFeedbackStateMachine`
    (``app.services.user_feedback_state_machine``).

    # ABAC 边界 (ADR-0049 §6 + ADR-0048 §7.0)

    - ``raw_content`` / ``metadata``: 仅用户本人/admin 可见, 陪诊师端**不返回**
    - ``admin_sanitized_summary``: admin 人工脱敏摘要, 陪诊师端可见
    - ``admin_resolution_summary``: 处理结论, admin/user 可见, 陪诊师 ABAC
    - ``companion_appeal``: 仅对应陪诊师可写, admin/user 可见

    本 task 只定义 ORM 字段; endpoint 层 ABAC 列裁剪 + schema 哨兵 由
    ``S3-DEV-004-FEEDBACK-API`` task 实现.
    """

    __tablename__ = "user_feedbacks"

    # ----- 复合 partial unique index + secondary indexes (ADR-0049 §3.1) -----
    #
    # Mirrors raw DDL in alembic migration; declared here so ``alembic check``
    # does not detect drift.
    #
    # uq_user_feedback_once_per_order_category: 防"同 user 对同 order 同 category"
    # 重复首条反馈 (parent IS NULL). 补充反馈 (parent IS NOT NULL) 与平台级
    # (order_id IS NULL) 不受此 unique 限.
    __table_args__ = (
        Index(
            "uq_user_feedback_once_per_order_category",
            "user_id",
            "order_id",
            "category",
            unique=True,
            postgresql_where=text(
                "feedback_parent_id IS NULL AND order_id IS NOT NULL"
            ),
        ),
        Index(
            "idx_user_feedbacks_module_time",
            "feedback_function_module",
            "created_at",
        ),
        Index(
            "idx_user_feedbacks_severity_status",
            "severity",
            "status",
        ),
        Index(
            "idx_user_feedbacks_companion_status",
            "companion_id",
            "status",
            postgresql_where=text("companion_id IS NOT NULL"),
        ),
        Index(
            "idx_user_feedbacks_parent",
            "feedback_parent_id",
            postgresql_where=text("feedback_parent_id IS NOT NULL"),
        ),
    )

    # ----- Identity -----

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    feedback_parent_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_feedbacks.id"),
        nullable=True,
        comment="补充反馈指向首条反馈 (ADR-0049 §3.2); NULL = 首条",
    )

    # ----- Three FK relationships (all nullable, ADR-0049 §3.1) -----

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
        comment="反馈提交人 user_id (非 NULL)",
    )

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id"),
        nullable=True,
        comment="可选关联订单 (NULL = 平台级反馈, ADR-0049 §3.1)",
    )

    companion_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("companion_profiles.id"),
        nullable=True,
        comment="可选关联陪诊师 (NULL = 非对陪诊师反馈)",
    )

    # ----- Classification -----

    feedback_function_module: Mapped[FeedbackFunctionModule] = mapped_column(
        Enum(
            FeedbackFunctionModule,
            name="feedback_function_module",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        comment="功能模块域 (ADR-0049 §3.1, 8 个枚举)",
    )

    category: Mapped[str] = mapped_column(
        String(length=64),
        nullable=False,
        comment="反馈类别 (服务态度/专业能力/平台流程/费用问题/隐私担忧/建议)",
    )

    severity: Mapped[FeedbackSeverity] = mapped_column(
        Enum(
            FeedbackSeverity,
            name="feedback_severity",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        comment="严重度 (urgent → 触发 alertmanager 告警)",
    )

    source: Mapped[FeedbackSource] = mapped_column(
        Enum(
            FeedbackSource,
            name="feedback_source",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        comment="提交来源 (user/customer_service/phone/offline)",
    )

    # ----- Content fields (ABAC 列裁剪由 endpoint 层负责) -----

    raw_content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="用户原文 — 仅 user/admin 可见, 陪诊师端 ABAC 拒",
    )

    admin_sanitized_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="admin 人工脱敏摘要 — 陪诊师端唯一可见的内容字段",
    )

    admin_resolution_summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="处理结论 — admin/user 可见, 陪诊师 ABAC",
    )

    companion_appeal: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="陪诊师申诉文字 — 仅对应陪诊师可写",
    )

    # ----- State machine -----

    status: Mapped[FeedbackStatus] = mapped_column(
        Enum(
            FeedbackStatus,
            name="feedback_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=FeedbackStatus.pending,
        comment="状态机当前态 (UserFeedbackStateMachine, ADR-0049 §4.1)",
    )

    handled_by_admin_id: Mapped[int | None] = mapped_column(
        _ADMIN_ID_TYPE,
        ForeignKey("admin_users.id"),
        nullable=True,
        comment="首次 admin_start_review 操作员 admin_id",
    )

    handled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="admin_start_review 时间",
    )

    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="closed 状态写入时间 (用于 30d append 窗口判断)",
    )

    # ----- Metadata / audit -----

    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        _JsonbType,
        nullable=False,
        default=dict,
        comment="自由扩展 (UA / IP / 截图链接索引等), ABAC: 仅 user/admin 可见",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="行创建时间 (immutable)",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# 30-day append window (ADR-0049 §4.1 closed → in_review)
# ---------------------------------------------------------------------------

CLOSED_APPEND_WINDOW_DAYS: Final[int] = 30
"""closed 状态下 user_append 允许的窗口 (30d). 超出 → API HTTP 410 Gone.

实际窗口判断在 :mod:`app.services.user_feedback_state_machine` 的
``can_user_append_when_closed`` helper, 由 S3-DEV-004-FEEDBACK-API 任务
内 endpoint 层调用.
"""
