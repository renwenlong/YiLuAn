"""add payment_callback_log table

Revision ID: c8d9e0f1a2b3
Revises: b7c8d9e0f1a2
Create Date: 2026-04-18 16:45:00.000000

P0-1（Action #1）：为支付回调引入幂等日志表。

设计要点
--------
* 唯一约束 ``uq_payment_callback_provider_txn (provider, transaction_id)``
  是幂等键。重复回调写入时会触发 ``IntegrityError``，应用层据此返回 200
  SUCCESS 而不再重复处理订单。
* 手写迁移（autogenerate 对 ``UniqueConstraint`` + ``Index`` 组合及
  ``Uuid`` 类型的处理在过往项目中出现过遗漏，参考
  ``docs/MIGRATION_AUDIT_2026-04-17.md`` 与历史迁移
  ``b7c8d9e0f1a2_align_payments_columns_and_verify_enums``）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8d9e0f1a2b3"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_callback_log",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("transaction_id", sa.String(length=128), nullable=False),
        sa.Column(
            "callback_type",
            sa.String(length=16),
            nullable=False,
            server_default="pay",
        ),
        sa.Column("out_trade_no", sa.String(length=64), nullable=True),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="processed",
        ),
        sa.Column("raw_body", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "provider",
            "transaction_id",
            name="uq_payment_callback_provider_txn",
        ),
    )
    op.create_index(
        "ix_payment_callback_log_out_trade_no",
        "payment_callback_log",
        ["out_trade_no"],
    )
    op.create_index(
        "ix_payment_callback_created_at",
        "payment_callback_log",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_callback_created_at",
        table_name="payment_callback_log",
    )
    op.drop_index(
        "ix_payment_callback_log_out_trade_no",
        table_name="payment_callback_log",
    )
    op.drop_constraint(
        "uq_payment_callback_provider_txn",
        "payment_callback_log",
        type_="unique",
    )
    op.drop_table("payment_callback_log")
