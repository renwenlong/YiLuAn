"""align payments columns & verify enums

Revision ID: b7c8d9e0f1a2
Revises: a50c6c117291
Create Date: 2026-04-17 23:15:00.000000

补齐 model 与 schema 不一致：
- payments: 新增 trade_no / prepay_id / refund_id / callback_raw 列及 trade_no 索引
- orderstatus enum: idempotent 追加 rejected_by_companion / expired（历史已追加，保留 IF NOT EXISTS 作双保险）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a50c6c117291"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """Helper: only add column if it does not already exist (PG)."""
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns(table)}
    if column.name not in existing:
        op.add_column(table, column)


def _drop_column_if_exists(table: str, column_name: str) -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = {c["name"] for c in insp.get_columns(table)}
    if column_name in existing:
        op.drop_column(table, column_name)


def _index_exists(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return any(ix["name"] == index_name for ix in insp.get_indexes(table))


def upgrade() -> None:
    # --- payments: 补齐 model 定义的 4 列 ---
    _add_column_if_missing(
        "payments",
        sa.Column("trade_no", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "payments",
        sa.Column("prepay_id", sa.String(length=128), nullable=True),
    )
    _add_column_if_missing(
        "payments",
        sa.Column("refund_id", sa.String(length=64), nullable=True),
    )
    _add_column_if_missing(
        "payments",
        sa.Column("callback_raw", sa.Text(), nullable=True),
    )

    # 索引：trade_no
    if not _index_exists("payments", "ix_payments_trade_no"):
        op.create_index("ix_payments_trade_no", "payments", ["trade_no"])

    # --- orderstatus enum: idempotent 追加缺失值 ---
    # 必须在 autocommit block 中执行 (PG 限制 ALTER TYPE ADD VALUE 不能进事务)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute(
                "ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'rejected_by_companion'"
            )
            op.execute(
                "ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'expired'"
            )


def downgrade() -> None:
    # 丢 index + 4 列；enum 值不 drop（PG 不支持 DROP VALUE 且有历史数据风险）
    if _index_exists("payments", "ix_payments_trade_no"):
        op.drop_index("ix_payments_trade_no", table_name="payments")
    _drop_column_if_exists("payments", "callback_raw")
    _drop_column_if_exists("payments", "refund_id")
    _drop_column_if_exists("payments", "prepay_id")
    _drop_column_if_exists("payments", "trade_no")
