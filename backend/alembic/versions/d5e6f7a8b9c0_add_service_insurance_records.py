"""add service_insurance_records table + insurance_status ENUM (S3-DEV-001-INSURANCE-DOMAIN)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-06-06 08:18:00.000000

ADR-0047 §3.3:
- service_insurance_records 表 (一单一保单, UNIQUE order_id)
- insurance_status ENUM 6 states
- partial index on (status) WHERE status IN ('pending_issue','issue_failed') for compensation cron
- orders.insurance_id 列 (nullable, FK service_insurance_records.id)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# admin_users.id is BigInteger on PG / Integer on SQLite (see admin_user.py).
_ADMIN_ID_TYPE = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

revision = "d5e6f7a8b9c0"
# Chain after CONTRACT (PR #200 先合 main, hash 89bdaf8);
# zero schema overlap — orders.insurance_id (本 PR 加) 与 orders.contract_id
# (CONTRACT PR 加) 是独立列。
# 不需 merge migration。 None-merge fix 仅改下面一行。
down_revision = "d5e6f7a8b9c1"
branch_labels = None
depends_on = None


INSURANCE_STATES = (
    "pending_issue",
    "active",
    "expired",
    "cancelled",
    "issue_failed",
    "manually_invalidated",
)


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        sa.Enum(*INSURANCE_STATES, name="insurance_status").create(bind, checkfirst=True)
        insurance_status = postgresql.ENUM(
            *INSURANCE_STATES, name="insurance_status", create_type=False
        )
    else:
        # SQLite/MySQL: VARCHAR + CHECK
        insurance_status = sa.Enum(*INSURANCE_STATES, name="insurance_status")

    op.create_table(
        "service_insurance_records",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if dialect == "postgresql" else None,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
            unique=True,
            comment="一单一保单, 禁重复出单 (ADR-0047 §3.3)",
        ),
        sa.Column(
            "product_name",
            sa.String(128),
            nullable=False,
            comment='保险产品名, 如 "陪诊责任险标准版"',
        ),
        sa.Column(
            "coverage_amount_cny",
            sa.Integer,
            nullable=False,
            comment="保额, 分单位整数 (ADR-0030 金额规范, 与 contract amount_cny 一致)",
        ),
        sa.Column(
            "vendor_name",
            sa.String(64),
            nullable=False,
            server_default="PLACEHOLDER_VENDOR",
            comment="保险公司; S3 用 PLACEHOLDER_VENDOR (PRD-003 §2.2)",
        ),
        sa.Column(
            "vendor_policy_no",
            sa.String(128),
            nullable=True,
            comment='vendor 保单号 (PRD-003 §3.3 AC-4 允许 PENDING); S3: "PLACEHOLDER-{order_id8}"',
        ),
        sa.Column(
            "status",
            insurance_status,
            nullable=False,
            server_default="pending_issue",
            comment="状态机由 InsuranceStateMachine 维护; 直接 UPDATE 禁",
        ),
        sa.Column(
            "retry_count",
            sa.SmallInteger,
            nullable=False,
            server_default="0",
            comment="补偿 cron retry 次数 (5min/30min/2h 三档, 上限 3)",
        ),
        sa.Column(
            "failure_reason",
            sa.Text,
            nullable=True,
            comment="最近一次失败的 error trace; AC#4",
        ),
        sa.Column(
            "issued_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="vendor 确认出单时间; status=active 时设",
        ),
        sa.Column(
            "invalidation_reason",
            sa.Text,
            nullable=True,
            comment="作废原因; status=manually_invalidated 时**必填** (AC#5)",
        ),
        sa.Column(
            "invalidated_by_admin_id",
            _ADMIN_ID_TYPE,
            sa.ForeignKey("admin_users.id"),
            nullable=True,
            comment="作废人 admin_user_id (BigInt PG / Int SQLite); manually_invalidated 必填 (AC#5)",  # noqa: E501
        ),
        sa.Column(
            "invalidated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="作废时间",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # Indexes — column-level ``unique=True`` on ``order_id`` 是代码上岸严紧与 ORM
    # ``mapped_column(... unique=True, ...)`` 镜像, alembic.autogenerate 则走 unique
    # constraint path — 不重复创建 unique index。
    # status 列加 plain index 供表扫。
    op.create_index(
        op.f("ix_service_insurance_records_status"),
        "service_insurance_records",
        ["status"],
        unique=False,
    )

    # Partial index for compensation cron — only scan rows the cron cares about.
    # SQLite doesn't support partial indexes the same way; fall back to full.
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX idx_insurance_records_compensation "
            "ON service_insurance_records(status, retry_count, updated_at) "
            "WHERE status IN ('pending_issue', 'issue_failed')"
        )
    else:
        op.create_index(
            "idx_insurance_records_compensation",
            "service_insurance_records",
            ["status", "retry_count", "updated_at"],
            unique=False,
        )

    # Add insurance_id nullable column to orders (ADR-0047 §3.3)
    # NOTE: contract_id 列由 CONTRACT-DOMAIN task 加, 不在本 migration scope.
    with op.batch_alter_table("orders") as batch:
        batch.add_column(
            sa.Column(
                "insurance_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("service_insurance_records.id"),
                nullable=True,
                comment="一单一保单, nullable 因保险不影响订单成立 (PRD-003 AC-5)",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table("orders") as batch:
        batch.drop_column("insurance_id")

    op.drop_index(
        "idx_insurance_records_compensation",
        table_name="service_insurance_records",
    )
    op.drop_index(
        op.f("ix_service_insurance_records_status"),
        table_name="service_insurance_records",
    )
    op.drop_table("service_insurance_records")

    if dialect == "postgresql":
        sa.Enum(name="insurance_status").drop(bind, checkfirst=True)
