"""add message/notification indexes

Revision ID: a8b9c0d1e2f3
Revises: f1a2b3c4d5e6
Create Date: 2026-04-17 18:00:00.000000

Purpose: 给聊天和通知表补齐查询常用索引，避免全表扫描。
- chat_messages.sender_id / created_at / is_read
- notifications.is_read / created_at

order_id（chat_messages）和 user_id（notifications）已有索引。
"""
from alembic import op


# revision identifiers, used by Alembic.
revision = "a8b9c0d1e2f3"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # chat_messages
    op.create_index(
        "ix_chat_messages_sender_id",
        "chat_messages",
        ["sender_id"],
    )
    op.create_index(
        "ix_chat_messages_created_at",
        "chat_messages",
        ["created_at"],
    )
    op.create_index(
        "ix_chat_messages_is_read",
        "chat_messages",
        ["is_read"],
    )
    # notifications
    op.create_index(
        "ix_notifications_is_read",
        "notifications",
        ["is_read"],
    )
    op.create_index(
        "ix_notifications_created_at",
        "notifications",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notifications_created_at", table_name="notifications")
    op.drop_index("ix_notifications_is_read", table_name="notifications")
    op.drop_index("ix_chat_messages_is_read", table_name="chat_messages")
    op.drop_index("ix_chat_messages_created_at", table_name="chat_messages")
    op.drop_index("ix_chat_messages_sender_id", table_name="chat_messages")
