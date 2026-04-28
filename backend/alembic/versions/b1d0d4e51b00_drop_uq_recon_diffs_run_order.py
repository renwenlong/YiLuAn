"""drop uq_recon_diffs_run_order index (M2 model/migration drift fix)

Revision ID: b1d0d4e51b00
Revises: a1d0d4e51a32
Create Date: 2026-04-28 17:15:00

ADR-0032 / TD-MONEY-01 M3 hotfix:
  M2 alembic 留下了 ``uq_recon_diffs_run_order`` 唯一索引 (run_id, order_id)，
  但模型层从未声明这个约束 → CI ``alembic check`` 报 drift。
  M3 增量对账明确要求"同一 run 内同 order 可有多 diff"（不同 kind / 多次 sweep
  失败重试），删掉这个 unique 反而更符合实际语义。
"""
from alembic import op


revision = "b1d0d4e51b00"
down_revision = "a1d0d4e51a32"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(
        "uq_recon_diffs_run_order",
        table_name="reconciliation_diffs",
    )


def downgrade() -> None:
    op.create_index(
        "uq_recon_diffs_run_order",
        "reconciliation_diffs",
        ["run_id", "order_id"],
        unique=True,
    )
