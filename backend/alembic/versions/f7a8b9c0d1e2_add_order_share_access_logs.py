"""add order_share_access_logs (S2-DEV-006 anomaly scanner)

Revision ID: f7a8b9c0d1e2
Revises: d860a0a0a001
Create Date: 2026-05-29 08:00:00.000000

ADR-0036 §2.4. Append-only audit log powering the 24h rolling-window
distinct-accessor anomaly scanner. Pure additive — no existing tables
touched.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "d860a0a0a001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_share_access_logs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "token_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("order_share_tokens.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("accessor_openid", sa.String(length=64), nullable=False),
        sa.Column("accessed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_share_access_token_time",
        "order_share_access_logs",
        ["token_id", "accessed_at"],
    )
    op.create_index(
        "ix_share_access_accessed_at",
        "order_share_access_logs",
        ["accessed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_share_access_accessed_at", table_name="order_share_access_logs")
    op.drop_index("ix_share_access_token_time", table_name="order_share_access_logs")
    op.drop_table("order_share_access_logs")
