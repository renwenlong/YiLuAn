"""S3-DEV-004-FEEDBACK-DOMAIN add user_feedbacks table + 4 ENUMs + UserFeedbackStateMachine

ADR-0049 §3.1 完整 schema + §4.1 状态机.

# 范围 (本 migration)

- 4 个 ENUM: feedback_status / feedback_severity / feedback_source / feedback_function_module
- ``user_feedbacks`` 表 (含 16 字段 + 5 索引 + 1 partial unique index)
- partial UNIQUE INDEX:
  ``(user_id, order_id, category) WHERE feedback_parent_id IS NULL AND order_id IS NOT NULL``

# 不在范围

- ``feedback_attachments`` 表 → S3-DEV-004-FEEDBACK-STORAGE (单独 migration)

# Downgrade caveat

drop_table 不会自动 drop PG ENUM 类型 (alembic autogen 缺陷). upgrade 由
column inline ``sa.Enum`` 隐式建 ENUM (PG); downgrade 必须**手动**显式 drop
ENUM (在 drop_table 之后, ENUM 已无引用).

# Three FK relationships (all nullable, ADR-0049 §3.1)

- ``user_id`` NOT NULL → ``users.id``: 反馈提交人 (必填)
- ``order_id`` NULL → ``orders.id``: 平台级反馈不绑订单
- ``companion_id`` NULL → ``companion_profiles.id``: 非对陪诊师反馈
- ``feedback_parent_id`` NULL → ``user_feedbacks.id``: 补充反馈 self-ref
- ``handled_by_admin_id`` NULL → ``admin_users.id``: admin_start_review 操作员

Revision ID: ec17fc201944
Revises: 7a8e1c2d4f60
Create Date: 2026-06-10 10:05:42.488556
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "ec17fc201944"
down_revision: Union[str, None] = "7a8e1c2d4f60"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 主表 — column inline sa.Enum 会自动 CREATE TYPE (PG); 不需要显式 create.
    op.create_table(
        "user_feedbacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "feedback_parent_id",
            sa.Uuid(),
            nullable=True,
            comment="补充反馈指向首条反馈 (ADR-0049 §3.2); NULL = 首条",
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=False,
            comment="反馈提交人 user_id (非 NULL)",
        ),
        sa.Column(
            "order_id",
            sa.Uuid(),
            nullable=True,
            comment="可选关联订单 (NULL = 平台级反馈, ADR-0049 §3.1)",
        ),
        sa.Column(
            "companion_id",
            sa.Uuid(),
            nullable=True,
            comment="可选关联陪诊师 (NULL = 非对陪诊师反馈)",
        ),
        sa.Column(
            "feedback_function_module",
            sa.Enum(
                "insurance",
                "contract",
                "ai_prep",
                "family_share",
                "service_package",
                "service_quality",
                "payment",
                "other",
                name="feedback_function_module",
            ),
            nullable=False,
            comment="功能模块域 (ADR-0049 §3.1, 8 个枚举)",
        ),
        sa.Column(
            "category",
            sa.String(length=64),
            nullable=False,
            comment="反馈类别 (服务态度/专业能力/平台流程/费用问题/隐私担忧/建议)",
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "normal",
                "important",
                "urgent",
                name="feedback_severity",
            ),
            nullable=False,
            comment="严重度 (urgent → 触发 alertmanager 告警)",
        ),
        sa.Column(
            "source",
            sa.Enum(
                "user",
                "customer_service",
                "phone",
                "offline",
                name="feedback_source",
            ),
            nullable=False,
            comment="提交来源 (user/customer_service/phone/offline)",
        ),
        sa.Column(
            "raw_content",
            sa.Text(),
            nullable=False,
            comment="用户原文 — 仅 user/admin 可见, 陪诊师端 ABAC 拒",
        ),
        sa.Column(
            "admin_sanitized_summary",
            sa.Text(),
            nullable=True,
            comment="admin 人工脱敏摘要 — 陪诊师端唯一可见的内容字段",
        ),
        sa.Column(
            "admin_resolution_summary",
            sa.Text(),
            nullable=True,
            comment="处理结论 — admin/user 可见, 陪诊师 ABAC",
        ),
        sa.Column(
            "companion_appeal",
            sa.Text(),
            nullable=True,
            comment="陪诊师申诉文字 — 仅对应陪诊师可写",
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "in_review",
                "resolved",
                "closed",
                "rejected",
                name="feedback_status",
            ),
            nullable=False,
            comment="状态机当前态 (UserFeedbackStateMachine, ADR-0049 §4.1)",
        ),
        sa.Column(
            "handled_by_admin_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
            comment="首次 admin_start_review 操作员 admin_id",
        ),
        sa.Column(
            "handled_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="admin_start_review 时间",
        ),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="closed 状态写入时间 (用于 30d append 窗口判断)",
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            comment="自由扩展 (UA / IP / 截图链接索引等), ABAC: 仅 user/admin 可见",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="行创建时间 (immutable)",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["companion_id"], ["companion_profiles.id"]),
        sa.ForeignKeyConstraint(["feedback_parent_id"], ["user_feedbacks.id"]),
        sa.ForeignKeyConstraint(["handled_by_admin_id"], ["admin_users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # 索引 (5 个: 1 partial unique + 2 partial + 2 普通 + 1 fk index)
    op.create_index(
        "idx_user_feedbacks_companion_status",
        "user_feedbacks",
        ["companion_id", "status"],
        unique=False,
        postgresql_where=sa.text("companion_id IS NOT NULL"),
    )
    op.create_index(
        "idx_user_feedbacks_module_time",
        "user_feedbacks",
        ["feedback_function_module", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_user_feedbacks_parent",
        "user_feedbacks",
        ["feedback_parent_id"],
        unique=False,
        postgresql_where=sa.text("feedback_parent_id IS NOT NULL"),
    )
    op.create_index(
        "idx_user_feedbacks_severity_status",
        "user_feedbacks",
        ["severity", "status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_feedbacks_user_id"),
        "user_feedbacks",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "uq_user_feedback_once_per_order_category",
        "user_feedbacks",
        ["user_id", "order_id", "category"],
        unique=True,
        postgresql_where=sa.text(
            "feedback_parent_id IS NULL AND order_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 反向: 先 drop indexes → drop table → drop ENUMs (顺序很重要, ENUM 被列引用
    # 时不能 drop, 必须先 drop 表)
    op.drop_index(
        "uq_user_feedback_once_per_order_category",
        table_name="user_feedbacks",
        postgresql_where=sa.text(
            "feedback_parent_id IS NULL AND order_id IS NOT NULL"
        ),
    )
    op.drop_index(op.f("ix_user_feedbacks_user_id"), table_name="user_feedbacks")
    op.drop_index(
        "idx_user_feedbacks_severity_status", table_name="user_feedbacks"
    )
    op.drop_index(
        "idx_user_feedbacks_parent",
        table_name="user_feedbacks",
        postgresql_where=sa.text("feedback_parent_id IS NOT NULL"),
    )
    op.drop_index(
        "idx_user_feedbacks_module_time", table_name="user_feedbacks"
    )
    op.drop_index(
        "idx_user_feedbacks_companion_status",
        table_name="user_feedbacks",
        postgresql_where=sa.text("companion_id IS NOT NULL"),
    )
    op.drop_table("user_feedbacks")

    # 显式 drop ENUM (autogen 不出, 不然 head 残留 PG type)
    if bind.dialect.name == "postgresql":
        sa.Enum(
            "pending",
            "in_review",
            "resolved",
            "closed",
            "rejected",
            name="feedback_status",
        ).drop(bind, checkfirst=True)
        sa.Enum(
            "normal",
            "important",
            "urgent",
            name="feedback_severity",
        ).drop(bind, checkfirst=True)
        sa.Enum(
            "user",
            "customer_service",
            "phone",
            "offline",
            name="feedback_source",
        ).drop(bind, checkfirst=True)
        sa.Enum(
            "insurance",
            "contract",
            "ai_prep",
            "family_share",
            "service_package",
            "service_quality",
            "payment",
            "other",
            name="feedback_function_module",
        ).drop(bind, checkfirst=True)
