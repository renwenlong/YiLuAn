"""add telemetry_events table

Revision ID: c1d2e3f4a5b7
Revises: b5c6d7e8f9a0
Create Date: 2026-05-25 08:35:00.000000

Observability — frontend funnel + error reporter sink.

设计要点
--------
* PG: ``payload`` / ``client_meta`` 落 ``JSONB``（可加 GIN 索引按 key 查）。
  SQLite: 退化为 ``JSON`` 文本，供测试用。
* 不存 PII（手机号 / 姓名 / 身份证）；schema 层 validator 是第一道闸，
  DB 层仅做长度与索引。
* ``user_id`` 可空（未登录埋点）；FK 走 ``SET NULL``，删用户时不阻塞。
* 索引：``event_type`` / ``created_at`` / ``user_id`` 覆盖 admin 列表 +
  漏斗按时间聚合 + 单用户排查三个最高频查询。
* 表名 / 索引名全部显式命名，PG 与 SQLite 双向 drop 干净。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "d2e3f4a5b6c8"
down_revision: Union[str, None] = "c1d2e3f4a5b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "telemetry_events",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "client_meta",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            nullable=True,
        ),
        sa.Column("client_ts", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_telemetry_events_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_telemetry_events_event_type",
        "telemetry_events",
        ["event_type"],
    )
    op.create_index(
        "ix_telemetry_events_created_at",
        "telemetry_events",
        ["created_at"],
    )
    op.create_index(
        "ix_telemetry_events_user_id",
        "telemetry_events",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_telemetry_events_user_id", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_created_at", table_name="telemetry_events")
    op.drop_index("ix_telemetry_events_event_type", table_name="telemetry_events")
    op.drop_table("telemetry_events")
