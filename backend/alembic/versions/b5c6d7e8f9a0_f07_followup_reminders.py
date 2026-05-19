"""F-07: followup_reminders table

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-05-19 04:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATUS_VALUES = ("pending", "sent", "failed", "cancelled")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        sa.Enum(*STATUS_VALUES, name="followupreminderstatus").create(
            bind, checkfirst=True
        )
        status_type = postgresql.ENUM(
            *STATUS_VALUES, name="followupreminderstatus", create_type=False
        )
        status_col = sa.Column(
            "status", status_type, nullable=False, server_default="pending"
        )
    else:
        status_col = sa.Column(
            "status",
            sa.Enum(*STATUS_VALUES, name="followupreminderstatus"),
            nullable=False,
            server_default="pending",
        )

    op.create_table(
        "followup_reminders",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("remind_at", sa.DateTime(timezone=True), nullable=False, index=True),
        status_col,
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("note", sa.String(length=140), nullable=True),
        sa.Column("provider_message_id", sa.String(length=64), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_followup_reminders_user_id", "followup_reminders", ["user_id"]
    )
    op.create_index(
        "ix_followup_reminders_order_id", "followup_reminders", ["order_id"]
    )
    op.create_index(
        "ix_followup_reminders_remind_at", "followup_reminders", ["remind_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_followup_reminders_remind_at", table_name="followup_reminders")
    op.drop_index("ix_followup_reminders_order_id", table_name="followup_reminders")
    op.drop_index("ix_followup_reminders_user_id", table_name="followup_reminders")
    op.drop_table("followup_reminders")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="followupreminderstatus").drop(bind, checkfirst=True)
