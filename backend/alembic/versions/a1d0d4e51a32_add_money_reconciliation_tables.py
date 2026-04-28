"""[ADR-0032 / TD-MONEY-01 M1] add money reconciliation tables + wallet_ledger

Revision ID: a1d0d4e51a32
Revises: c0ffee029001
Create Date: 2026-04-28 14:35:00.000000

新增 4 张表 + 7 个 PG 枚举类型（ADR §3.3 与 §3.5）：

- ``reconciliation_runs``      (recon_run_kind / recon_run_status)
- ``reconciliation_diffs``     (recon_diff_kind / recon_diff_status)
- ``reconciliation_actions``   (recon_action_kind)
- ``wallet_ledger``            (wallet_ledger_direction / wallet_ledger_reason)

**所有枚举手写 ``op.execute("CREATE TYPE ...")``，禁止 autogenerate**（历史多次
``ALTER TYPE`` 漂移教训）。downgrade 反向 ``DROP TABLE → DROP TYPE``。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a1d0d4e51a32"
down_revision: Union[str, None] = "c0ffee029001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Enum definitions (PG 类型名 → 取值列表)
# ---------------------------------------------------------------------------
_ENUMS: list[tuple[str, tuple[str, ...]]] = [
    ("recon_run_kind", ("full_t1", "incremental")),
    ("recon_run_status", ("running", "success", "partial", "failed")),
    (
        "recon_diff_kind",
        (
            "missing_payment",
            "orphan_payment",
            "amount_mismatch",
            "status_mismatch",
        ),
    ),
    (
        "recon_diff_status",
        ("pending", "matched", "mismatched", "compensated", "closed"),
    ),
    (
        "recon_action_kind",
        (
            "auto_replay",
            "manual_close",
            "manual_refund",
            "manual_credit",
            "escalate",
        ),
    ),
    ("wallet_ledger_direction", ("in", "out")),
    ("wallet_ledger_reason", ("pay", "refund", "adjust")),
]


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _enum(name: str, values: tuple[str, ...]):
    """构造与既有 PG 类型对齐的列类型。

    PG：使用 ``postgresql.ENUM(create_type=False)``，确保不会重复触发
    ``CREATE TYPE``（我们在 upgrade 起始已显式 ``DO $$ CREATE TYPE ... $$``）。
    SQLite：退化为 ``sa.String(32)``，避免不同方言混乱。
    """
    if op.get_bind().dialect.name == "postgresql":
        return postgresql.ENUM(
            *values, name=name, create_type=False
        )
    return sa.String(length=32)


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # 1) 在 PG 上显式建枚举
    if is_pg:
        for type_name, values in _ENUMS:
            quoted = ", ".join(f"'{v}'" for v in values)
            op.execute(
                "DO $$ BEGIN "
                f"CREATE TYPE {type_name} AS ENUM ({quoted}); "
                "EXCEPTION WHEN duplicate_object THEN NULL; "
                "END $$;"
            )

    enum_lookup = {name: vals for name, vals in _ENUMS}

    # 2) reconciliation_runs
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "kind",
            _enum("recon_run_kind", enum_lookup["recon_run_kind"]),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("recon_run_status", enum_lookup["recon_run_status"]),
            nullable=False,
            server_default="running",
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("orders_scanned", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diffs_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "diffs_auto_fixed", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("triggered_by", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_recon_runs_window",
        "reconciliation_runs",
        ["window_start", "window_end"],
    )
    op.create_index(
        "ix_recon_runs_status",
        "reconciliation_runs",
        ["status", "started_at"],
    )

    # 3) reconciliation_diffs
    op.create_table(
        "reconciliation_diffs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("reconciliation_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_txn_id", sa.String(length=128), nullable=True),
        sa.Column(
            "kind",
            _enum("recon_diff_kind", enum_lookup["recon_diff_kind"]),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum("recon_diff_status", enum_lookup["recon_diff_status"]),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("business_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("payment_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("ledger_amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("business_status", sa.String(length=32), nullable=True),
        sa.Column("payment_status", sa.String(length=32), nullable=True),
        sa.Column("ledger_status", sa.String(length=32), nullable=True),
        sa.Column(
            "auto_retry_count", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # 部分唯一索引：仅在 PG 上生效；SQLite 用普通 index 兜底
    if is_pg:
        op.create_index(
            "uq_recon_diffs_run_order",
            "reconciliation_diffs",
            ["run_id", "order_id"],
            unique=True,
            postgresql_where=sa.text("order_id IS NOT NULL"),
        )
    else:
        op.create_index(
            "uq_recon_diffs_run_order",
            "reconciliation_diffs",
            ["run_id", "order_id"],
            unique=False,
        )
    op.create_index(
        "ix_recon_diffs_status",
        "reconciliation_diffs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_recon_diffs_provider_txn",
        "reconciliation_diffs",
        ["provider", "provider_txn_id"],
    )

    # 4) reconciliation_actions
    op.create_table(
        "reconciliation_actions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "diff_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("reconciliation_diffs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "kind",
            _enum("recon_action_kind", enum_lookup["recon_action_kind"]),
            nullable=False,
        ),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_recon_actions_diff",
        "reconciliation_actions",
        ["diff_id", "created_at"],
    )

    # 5) wallet_ledger
    op.create_table(
        "wallet_ledger",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("order_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("provider_txn_id", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "direction",
            _enum(
                "wallet_ledger_direction", enum_lookup["wallet_ledger_direction"]
            ),
            nullable=False,
        ),
        sa.Column(
            "reason",
            _enum("wallet_ledger_reason", enum_lookup["wallet_ledger_reason"]),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "provider_txn_id",
            "direction",
            name="uq_wallet_ledger_provider_txn_direction",
        ),
    )
    op.create_index("ix_wallet_ledger_user_id", "wallet_ledger", ["user_id"])
    op.create_index("ix_wallet_ledger_order_id", "wallet_ledger", ["order_id"])
    op.create_index(
        "ix_wallet_ledger_occurred_at", "wallet_ledger", ["occurred_at"]
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------
def downgrade() -> None:
    is_pg = op.get_bind().dialect.name == "postgresql"

    # 反向 DROP TABLE
    op.drop_index("ix_wallet_ledger_occurred_at", table_name="wallet_ledger")
    op.drop_index("ix_wallet_ledger_order_id", table_name="wallet_ledger")
    op.drop_index("ix_wallet_ledger_user_id", table_name="wallet_ledger")
    op.drop_table("wallet_ledger")

    op.drop_index(
        "ix_recon_actions_diff", table_name="reconciliation_actions"
    )
    op.drop_table("reconciliation_actions")

    op.drop_index(
        "ix_recon_diffs_provider_txn", table_name="reconciliation_diffs"
    )
    op.drop_index("ix_recon_diffs_status", table_name="reconciliation_diffs")
    op.drop_index("uq_recon_diffs_run_order", table_name="reconciliation_diffs")
    op.drop_table("reconciliation_diffs")

    op.drop_index("ix_recon_runs_status", table_name="reconciliation_runs")
    op.drop_index("ix_recon_runs_window", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")

    # 然后 DROP TYPE（PG 才需要）
    if is_pg:
        for type_name, _values in reversed(_ENUMS):
            op.execute(f"DROP TYPE IF EXISTS {type_name}")
