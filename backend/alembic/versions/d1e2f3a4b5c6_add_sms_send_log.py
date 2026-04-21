"""add sms_send_log table

Revision ID: d1e2f3a4b5c6
Revises: 6bf94c0a3831
Create Date: 2026-04-21 21:40:00.000000

A21-02b / D-033 — SMS send audit log.

设计要点（5 项决策落地）
----------------------
* 字段集不含 ``params`` —— OTP 明文不入库，避免 PII 二次泄漏。
* phone 列方案 D —— 双列 ``phone_masked`` + ``phone_hash``（SHA256 + salt）。
* 唯一约束方案 A —— 无 DB 唯一约束；OTP 反爆破由业务层 / Redis
  限流（commit ce4259e）兜底。
* 写入入口方案 A —— 在 SMS factory 的 logging wrapper 自动落库；
  各 ``Provider.send_otp/send_notification`` 实现不变。
* 表 TTL 字段 ``expires_at`` 与 D-027 / payment_callback_log 一致，
  应用层填 ``now() + 90d``，由 TD-OPS-02 清理 job 统一回收。

Migration 风格
--------------
完全手写 ``op.create_table`` + ``op.create_index``。**不用** ``batch_alter_table``
—— 参考 A21-02-partial 教训（commit 38897f6），SQLite 的 batch 模式会
重写无名约束并丢失字段元信息。表名 / 索引名全部显式命名以便 PG/SQLite 双向
干净 drop。

PG 真机验证待补（本 commit 仅本地 SQLite ``alembic upgrade head`` /
``downgrade -1`` 双向验证通过）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "6bf94c0a3831"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sms_send_log",
        sa.Column(
            "id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("phone_masked", sa.String(length=20), nullable=False),
        sa.Column("phone_hash", sa.String(length=64), nullable=False),
        sa.Column("template_code", sa.String(length=64), nullable=False),
        sa.Column("sign_name", sa.String(length=32), nullable=True),
        sa.Column("biz_id", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("response_code", sa.String(length=64), nullable=True),
        sa.Column("response_msg", sa.String(length=512), nullable=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            nullable=True,
        ),
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
            name="fk_sms_send_log_user_id_users",
            ondelete="SET NULL",
        ),
    )
    op.create_index(
        "ix_sms_send_log_phone_hash",
        "sms_send_log",
        ["phone_hash"],
    )
    op.create_index(
        "ix_sms_send_log_biz_id",
        "sms_send_log",
        ["biz_id"],
    )
    op.create_index(
        "ix_sms_send_log_created_at",
        "sms_send_log",
        ["created_at"],
    )
    op.create_index(
        "ix_sms_send_log_expires_at",
        "sms_send_log",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_sms_send_log_expires_at", table_name="sms_send_log")
    op.drop_index("ix_sms_send_log_created_at", table_name="sms_send_log")
    op.drop_index("ix_sms_send_log_biz_id", table_name="sms_send_log")
    op.drop_index("ix_sms_send_log_phone_hash", table_name="sms_send_log")
    op.drop_table("sms_send_log")
