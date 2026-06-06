"""add service_contracts table + contract_status ENUM + immutable_fields trigger

(S3-DEV-001-CONTRACT-DOMAIN)

Revision ID: d5e6f7a8b9c1
Revises: d5e6f7a8b9c0
Create Date: 2026-06-06 08:28:00.000000

ADR-0047 §3.1 完整 schema + ADR-0046 §3.3 第 3 层 WORM 防御 (DB trigger):
- contract_status ENUM 6 状态
- service_contracts 表 (一单一合同 UNIQUE order_id + contract_hash UNIQUE)
- partial index on (status) WHERE status IN ('pending_generation', 'generation_failed')
- immutable_fields_guard BEFORE UPDATE trigger (PL/pgSQL, 拒 8 immutable 字段改动)
- orders.contract_id nullable FK (S3 启动后新订单, 不回填历史)
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "d5e6f7a8b9c1"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


CONTRACT_STATES = (
    "pending_generation",
    "generating",
    "active",
    "generation_failed",
    "generation_permanently_failed",
    "manually_invalidated",
)


# Immutable fields list (must match app/models/service_contract.py IMMUTABLE_FIELDS).
# Drift here vs the Python sentinel will fail the runtime sentinel test.
IMMUTABLE_FIELDS_SQL = [
    "id",
    "order_id",
    "template_version",
    "contract_hash",
    "hash_inputs",
    "storage_blob_path",
    "generated_at",
    "is_immutable",
    "created_at",
]


# PL/pgSQL trigger body — checks each immutable field; raises if OLD != NEW.
# Single SQL statement so all-or-nothing within the UPDATE.
_TRIGGER_BODY_SQL = """
CREATE OR REPLACE FUNCTION service_contracts_immutable_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.id IS DISTINCT FROM NEW.id) THEN
        RAISE EXCEPTION 'service_contracts.id is immutable (ADR-0046 §3.3 layer 3)';
    END IF;
    IF (OLD.order_id IS DISTINCT FROM NEW.order_id) THEN
        RAISE EXCEPTION 'service_contracts.order_id is immutable';
    END IF;
    IF (OLD.template_version IS DISTINCT FROM NEW.template_version) THEN
        RAISE EXCEPTION 'service_contracts.template_version is immutable';
    END IF;
    IF (OLD.contract_hash IS DISTINCT FROM NEW.contract_hash) THEN
        RAISE EXCEPTION 'service_contracts.contract_hash is immutable';
    END IF;
    IF (OLD.hash_inputs IS DISTINCT FROM NEW.hash_inputs) THEN
        RAISE EXCEPTION 'service_contracts.hash_inputs is immutable';
    END IF;
    -- storage_blob_path: NULL → non-NULL allowed (first write), non-NULL → other not allowed
    IF (OLD.storage_blob_path IS NOT NULL
        AND OLD.storage_blob_path IS DISTINCT FROM NEW.storage_blob_path) THEN
        RAISE EXCEPTION 'service_contracts.storage_blob_path is immutable once set';
    END IF;
    -- generated_at: NULL → non-NULL allowed (first generation), non-NULL → other not allowed
    IF (OLD.generated_at IS NOT NULL
        AND OLD.generated_at IS DISTINCT FROM NEW.generated_at) THEN
        RAISE EXCEPTION 'service_contracts.generated_at is immutable once set';
    END IF;
    IF (OLD.is_immutable IS DISTINCT FROM NEW.is_immutable) THEN
        RAISE EXCEPTION 'service_contracts.is_immutable cannot be flipped';
    END IF;
    IF (OLD.created_at IS DISTINCT FROM NEW.created_at) THEN
        RAISE EXCEPTION 'service_contracts.created_at is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_CREATE_TRIGGER_SQL = """
CREATE TRIGGER service_contracts_immutable_guard_trigger
    BEFORE UPDATE ON service_contracts
    FOR EACH ROW
    EXECUTE FUNCTION service_contracts_immutable_guard();
"""

_DROP_TRIGGER_SQL = (
    "DROP TRIGGER IF EXISTS service_contracts_immutable_guard_trigger " "ON service_contracts;"
)

_DROP_TRIGGER_FN_SQL = "DROP FUNCTION IF EXISTS service_contracts_immutable_guard();"


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # (a) CREATE TYPE contract_status ENUM
    if dialect == "postgresql":
        sa.Enum(*CONTRACT_STATES, name="contract_status").create(bind, checkfirst=True)
        contract_status = postgresql.ENUM(
            *CONTRACT_STATES, name="contract_status", create_type=False
        )
        hash_inputs_type = postgresql.JSONB()
    else:
        contract_status = sa.Enum(*CONTRACT_STATES, name="contract_status")
        hash_inputs_type = sa.JSON()

    # (b) CREATE TABLE service_contracts
    op.create_table(
        "service_contracts",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()") if dialect == "postgresql" else None,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=False,
            unique=True,
            comment="一单一合同 UNIQUE (immutable)",
        ),
        sa.Column(
            "template_version",
            sa.String(32),
            nullable=False,
            comment="合同模板 semver (immutable)",
        ),
        sa.Column(
            "contract_hash",
            sa.String(64),
            nullable=False,
            unique=True,
            comment="SHA-256 hex 64-char UNIQUE (immutable)",
        ),
        sa.Column(
            "hash_inputs",
            hash_inputs_type,
            nullable=False,
            comment="ADR-0046 §3.2 hash 原材料 JSONB (immutable)",
        ),
        sa.Column(
            "storage_blob_path",
            sa.String(512),
            nullable=True,
            comment="contracts/{YYYY}/{MM}/{order}_{hash}.pdf (immutable 一旦写入)",
        ),
        sa.Column(
            "status",
            contract_status,
            nullable=False,
            server_default="pending_generation",
        ),
        sa.Column(
            "retry_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column("last_error_trace", sa.Text, nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="status=active 时设 (immutable 一旦写入)",
        ),
        sa.Column(
            "is_immutable",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("TRUE"),
            comment="WORM 标记 (immutable)",
        ),
        sa.Column(
            "invalidation_reason",
            sa.Text,
            nullable=True,
            comment="必填 when status=manually_invalidated",
        ),
        sa.Column(
            "invalidated_by_admin_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
            comment="必填 when status=manually_invalidated",
        ),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            comment="immutable",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # (c) Indexes
    op.create_index(
        "idx_service_contracts_order_id",
        "service_contracts",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        "idx_service_contracts_contract_hash",
        "service_contracts",
        ["contract_hash"],
        unique=False,
    )

    # Partial index for compensation cron — only scan rows it cares about
    if dialect == "postgresql":
        op.execute(
            "CREATE INDEX idx_service_contracts_compensation "
            "ON service_contracts(status, retry_count, updated_at) "
            "WHERE status IN ('pending_generation', 'generation_failed')"
        )
    else:
        # SQLite: full index fallback (no partial index syntax compatibility)
        op.create_index(
            "idx_service_contracts_compensation",
            "service_contracts",
            ["status", "retry_count", "updated_at"],
            unique=False,
        )

    # (d) CREATE TRIGGER immutable_fields_guard (PG only — SQLite has no PL/pgSQL)
    if dialect == "postgresql":
        op.execute(_TRIGGER_BODY_SQL)
        op.execute(_CREATE_TRIGGER_SQL)

    # (e) Add orders.contract_id (nullable, FK service_contracts)
    # Note: orders.insurance_id already added by d5e6f7a8b9c0 (INSURANCE-DOMAIN)
    with op.batch_alter_table("orders") as batch:
        batch.add_column(
            sa.Column(
                "contract_id",
                sa.Uuid(as_uuid=True),
                sa.ForeignKey("service_contracts.id"),
                nullable=True,
                comment="一单一合同 nullable (PRD-003 §AC-5 订单不依赖合同)",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # Drop in reverse order

    with op.batch_alter_table("orders") as batch:
        batch.drop_column("contract_id")

    if dialect == "postgresql":
        op.execute(_DROP_TRIGGER_SQL)
        op.execute(_DROP_TRIGGER_FN_SQL)

    op.drop_index(
        "idx_service_contracts_compensation",
        table_name="service_contracts",
    )
    op.drop_index(
        "idx_service_contracts_contract_hash",
        table_name="service_contracts",
    )
    op.drop_index(
        "idx_service_contracts_order_id",
        table_name="service_contracts",
    )

    op.drop_table("service_contracts")

    if dialect == "postgresql":
        sa.Enum(name="contract_status").drop(bind, checkfirst=True)
