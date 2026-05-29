"""add order_share_tokens + ai_digests (W20 Top1 family companion)

Revision ID: a1b2c3d4e5f6
Revises: d729321e2784
Create Date: 2026-05-29 02:00:00.000000

ADR-0036 §2.3 OrderShareToken + PRD-001 v1.2 §4 AIDigest.
S2-DEV-001 (W20-D1) data model task. Pure additive — no existing
tables touched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d860a0a0a001"
down_revision: Union[str, None] = "d729321e2784"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_share_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column(
            "share_scope",
            sa.String(length=16),
            nullable=False,
            server_default="full",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("first_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_accessor_openid", sa.String(length=64), nullable=True),
        sa.Column(
            "distinct_accessor_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token", name="uq_order_share_tokens_token"),
    )
    op.create_index(
        "ix_order_share_tokens_order_id",
        "order_share_tokens",
        ["order_id"],
    )
    op.create_index(
        "ix_order_share_tokens_created_by",
        "order_share_tokens",
        ["created_by"],
    )
    op.create_index(
        "ix_order_share_tokens_expires_at",
        "order_share_tokens",
        ["expires_at"],
    )

    op.create_table(
        "ai_digests",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column(
            "cost_yuan",
            sa.Numeric(10, 4),
            nullable=False,
            server_default="0.0000",
        ),
        sa.Column("degraded_reason", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_ai_digests_order_id"),
    )
    op.create_index("ix_ai_digests_status", "ai_digests", ["status"])
    op.create_index("ix_ai_digests_created_at", "ai_digests", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_digests_created_at", table_name="ai_digests")
    op.drop_index("ix_ai_digests_status", table_name="ai_digests")
    op.drop_table("ai_digests")

    op.drop_index(
        "ix_order_share_tokens_expires_at", table_name="order_share_tokens"
    )
    op.drop_index(
        "ix_order_share_tokens_created_by", table_name="order_share_tokens"
    )
    op.drop_index(
        "ix_order_share_tokens_order_id", table_name="order_share_tokens"
    )
    op.drop_table("order_share_tokens")
