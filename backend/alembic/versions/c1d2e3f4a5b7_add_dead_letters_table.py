"""[W19 / TD-DEAD-LETTER] add dead_letters table for failed side-effect ops queue

Revision ID: c1d2e3f4a5b7
Revises: b5c6d7e8f9a0
Create Date: 2026-05-25 08:40:00.000000

新增 ``dead_letters`` 表：用于持久化「主流程已成功但副作用失败」的事件
（如 reject_order / force-cancel 自动退款失败），供运维人工补偿或重放 cron 消费。

PG：``payload`` 使用 ``JSONB``；``status`` 使用显式枚举 ``dead_letter_status``。
SQLite：退化为 ``JSON`` + ``String(32)``，保留测试兼容性。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c1d2e3f4a5b7"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ENUM_NAME = "dead_letter_status"
_ENUM_VALUES = ("pending", "resolved")


def _is_pg() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _status_col_type():
    if _is_pg():
        return postgresql.ENUM(*_ENUM_VALUES, name=_ENUM_NAME, create_type=False)
    return sa.String(length=32)


def _json_col_type():
    if _is_pg():
        return postgresql.JSONB()
    return sa.JSON()


def upgrade() -> None:
    if _is_pg():
        quoted = ", ".join(f"'{v}'" for v in _ENUM_VALUES)
        op.execute(
            "DO $$ BEGIN "
            f"CREATE TYPE {_ENUM_NAME} AS ENUM ({quoted}); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )

    op.create_table(
        "dead_letters",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("channel", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=True),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("payload", _json_col_type(), nullable=True),
        sa.Column(
            "status",
            _status_col_type(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_dead_letters_status_created",
        "dead_letters",
        ["status", "created_at"],
    )
    op.create_index("ix_dead_letters_channel", "dead_letters", ["channel"])
    op.create_index("ix_dead_letters_target_id", "dead_letters", ["target_id"])


def downgrade() -> None:
    op.drop_index("ix_dead_letters_target_id", table_name="dead_letters")
    op.drop_index("ix_dead_letters_channel", table_name="dead_letters")
    op.drop_index("ix_dead_letters_status_created", table_name="dead_letters")
    op.drop_table("dead_letters")
    if _is_pg():
        op.execute(f"DROP TYPE IF EXISTS {_ENUM_NAME}")
