"""add_worm_status_fields_to_service_contracts

S3-DEV-001-CONTRACT-WORM-COMPENSATION migration.

加 3 个字段到 service_contracts:
- worm_status ENUM(applied, pending_retry, permanently_failed) default 'applied'
- worm_retry_count INT default 0
- worm_last_retry_at TIMESTAMPTZ nullable

业务语义 (ADR-0047 + 刻晴 T4 spec):
- contract_storage.put_contract 调 put_if_absent 成功后再调 _set_worm_policy_if_azure
- _set_worm_policy_if_azure raise → ContractService 写 worm_status=pending_retry
- contract_worm_repair cron 每小时 SELECT worm_status=pending_retry → 重新 set
- 3 次失败 → worm_status=permanently_failed + 高优 alert

默认 'applied' (而非 nullable / pending_retry) 因为:
  - 已存 active 合同 backfill = 'applied' (历史上 Local backend / Azure mock 都成功)
  - 新写: contract_storage 一定 set 一个 worm_status (成功=applied / 失败=pending_retry)
  - 无 worm 概念 (Local backend) 也是 'applied' 语义 — WORM 是 Azure-only orthogonal,
    Local 不区分 = 默认 'applied' 简洁安全

Index:
  - service_contracts(worm_status, worm_retry_count, worm_last_retry_at)
    WHERE worm_status = 'pending_retry'
    (compensation cron scan; 等价 generation_failed 的 partial-index 模式)

Revision ID: 579fc0fbccaa
Revises: e7f8a9b0c1d2
Create Date: 2026-06-08 13:04:32.675597
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '579fc0fbccaa'
down_revision: Union[str, None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


WORM_STATUS_VALUES = ("applied", "pending_retry", "permanently_failed")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # PG 路径: 显式建 ENUM type, 再加 column 引用之.
        worm_status_enum = postgresql.ENUM(
            *WORM_STATUS_VALUES,
            name="contract_worm_status",
            create_type=False,
        )
        worm_status_enum.create(bind, checkfirst=True)

        op.add_column(
            "service_contracts",
            sa.Column(
                "worm_status",
                postgresql.ENUM(
                    *WORM_STATUS_VALUES,
                    name="contract_worm_status",
                    create_type=False,
                ),
                nullable=False,
                server_default=sa.text("'applied'::contract_worm_status"),
                comment="WORM 应用状态: applied (Azure Locked policy 已生效) / "
                        "pending_retry (put_if_absent 成功但 set_immutability_policy "
                        "raise, 等 compensation cron) / permanently_failed "
                        "(3 次 cron retry 全失败, 触发高优 alert).",
            ),
        )
    else:
        # SQLite 路径 (test fixture): 用 VARCHAR(32) + CHECK constraint mimic ENUM.
        op.add_column(
            "service_contracts",
            sa.Column(
                "worm_status",
                sa.String(32),
                nullable=False,
                server_default="applied",
                comment="WORM 应用状态 (SQLite 用 VARCHAR + CHECK mimic PG ENUM).",
            ),
        )
        # 加 CHECK 限值.
        with op.batch_alter_table("service_contracts") as batch_op:
            batch_op.create_check_constraint(
                "ck_service_contracts_worm_status",
                "worm_status IN ('applied', 'pending_retry', 'permanently_failed')",
            )

    op.add_column(
        "service_contracts",
        sa.Column(
            "worm_retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
            comment="WORM policy compensation cron 累计 retry 次数; >= WORM_RETRY_CAP → "
                    "worm_status=permanently_failed.",
        ),
    )
    op.add_column(
        "service_contracts",
        sa.Column(
            "worm_last_retry_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            comment="最近一次 WORM compensation cron 尝试时间; 用于退避策略与告警.",
        ),
    )

    # Compensation cron scan partial index — 只索 pending_retry 行
    # (绝大多数行 = applied, 不进索引), 等价 generation_failed 现有
    # idx_service_contracts_compensation 模式.
    if dialect == "postgresql":
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_contracts_worm_compensation
              ON service_contracts(worm_status, worm_retry_count, worm_last_retry_at)
              WHERE worm_status = 'pending_retry'
            """
        )
    else:
        # SQLite: partial index 也支持但用 op.create_index 比较挑剔, 用 raw DDL 一致.
        op.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_service_contracts_worm_compensation
              ON service_contracts(worm_status, worm_retry_count, worm_last_retry_at)
              WHERE worm_status = 'pending_retry'
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    op.execute("DROP INDEX IF EXISTS idx_service_contracts_worm_compensation")

    if dialect == "postgresql":
        op.drop_column("service_contracts", "worm_last_retry_at")
        op.drop_column("service_contracts", "worm_retry_count")
        op.drop_column("service_contracts", "worm_status")
        # 删 ENUM type (没 column 引用后才能 drop).
        worm_status_enum = postgresql.ENUM(
            *WORM_STATUS_VALUES,
            name="contract_worm_status",
            create_type=False,
        )
        worm_status_enum.drop(bind, checkfirst=True)
    else:
        # SQLite: batch_alter_table drop column + check constraint.
        with op.batch_alter_table("service_contracts") as batch_op:
            batch_op.drop_constraint("ck_service_contracts_worm_status", type_="check")
            batch_op.drop_column("worm_last_retry_at")
            batch_op.drop_column("worm_retry_count")
            batch_op.drop_column("worm_status")
