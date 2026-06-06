"""S3-DEV-001-USER-AUDIT: user_audit_logs table for contract/insurance audit trail

ADR-0047 §3.5 + §6.3 — 用户侧合同/保险审计独立表 (admin 操作仍走 admin_audit_logs)。

3 action: contract_acceptance_clicked / contract_viewed / insurance_terms_viewed
PIPL/民法典电子合同取证: user_agent + client_ip 必填, 反代提取真实 IP,
缺失写 0.0.0.0 + missing_ip=true metadata.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-06-06 16:25:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7f8a9b0c1d2"
# chain after INSURANCE-DOMAIN (避免与 CONTRACT-DOMAIN 双 head;
# 与本表无 schema overlap)
down_revision: Union[str, None] = "d5e6f7a8b9c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create user_audit_logs table for contract/insurance user-side audit trail."""
    op.create_table(
        "user_audit_logs",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            nullable=False,
            comment="UUID primary key",
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            comment="行为发起用户 (FK users.id, ADR-0047 §3.5)",
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=True,
            comment="关联订单 (可选, 查看保障条款无订单场景为 NULL)",
        ),
        sa.Column(
            "action",
            sa.String(64),
            nullable=False,
            comment=(
                "行为类型: contract_acceptance_clicked / contract_viewed / "
                "insurance_terms_viewed"
            ),
        ),
        sa.Column(
            "audit_metadata",
            postgresql.JSONB().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
            server_default=sa.text("'{}'::jsonb")
            if op.get_context().dialect.name == "postgresql"
            else sa.text("'{}'"),
            comment="扩展元数据 (template_version / missing_ip / 其他取证信息)",
        ),
        sa.Column(
            "user_agent",
            sa.Text,
            nullable=False,
            comment="User-Agent 字符串 (PIPL/民法典电子合同取证, 刻晴 #3 补充)",
        ),
        sa.Column(
            "client_ip",
            sa.String(45),
            nullable=False,
            comment="真实客户端 IP (反代提取, 缺失写 0.0.0.0; 支持 IPv6 故 45 字符)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="创建时间 (UTC)",
        ),
        comment="用户侧合同/保险审计 (ADR-0047 §3.5, 与 admin_audit_logs 物理隔离)",
    )

    # ADR-0047 §3.5 acceptance criteria #1: 2 indexes
    op.create_index(
        "idx_user_audit_logs_user_time",
        "user_audit_logs",
        ["user_id", sa.text("created_at DESC")],
    )
    op.create_index(
        "idx_user_audit_logs_order_action",
        "user_audit_logs",
        ["order_id", "action"],
    )


def downgrade() -> None:
    op.drop_index("idx_user_audit_logs_order_action", table_name="user_audit_logs")
    op.drop_index("idx_user_audit_logs_user_time", table_name="user_audit_logs")
    op.drop_table("user_audit_logs")
