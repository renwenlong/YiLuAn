"""add preparation_packages and prompt_versions

S3-DEV-002-PREP-PACKAGE-MIGRATION.

ADR-0048 §7.1 / §5: introduce the S3 structured AI prep package
storage. This is intentionally separate from S2 ``ai_digests``:
``ai_digests`` stores one family-facing text summary, while
``preparation_packages`` stores four structured content blocks plus
AI generation metadata for ABAC projections.

Revision ID: 6bc9f3d4a001
Revises: 579fc0fbccaa
Create Date: 2026-06-09 07:45:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "6bc9f3d4a001"
down_revision: Union[str, None] = "579fc0fbccaa"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


PREP_STATUS_VALUES = (
    "pending",
    "generating",
    "active",
    "active_fallback_template",
    "generation_failed",
)


def _json_type():
    """JSONB on Postgres, JSON on SQLite/dev tests."""
    return sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _prep_status_type(native: bool = True):
    return sa.Enum(
        *PREP_STATUS_VALUES,
        name="prep_status",
        native_enum=native,
        length=32,
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        prep_status = postgresql.ENUM(
            *PREP_STATUS_VALUES,
            name="prep_status",
            create_type=False,
        )
        prep_status.create(bind, checkfirst=True)
        status_column_type = postgresql.ENUM(
            *PREP_STATUS_VALUES,
            name="prep_status",
            create_type=False,
        )
        status_default = sa.text("'pending'::prep_status")
    else:
        status_column_type = _prep_status_type(native=False)
        status_default = sa.text("'pending'")

    op.create_table(
        "prompt_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("git_commit_hash", sa.String(length=40), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.UniqueConstraint("version", name="uq_prompt_versions_version"),
    )

    op.create_table(
        "preparation_packages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            status_column_type,
            nullable=False,
            server_default=status_default,
        ),
        sa.Column("carry_items", _json_type(), nullable=True),
        sa.Column("pre_visit_notes", _json_type(), nullable=True),
        sa.Column("possible_questions", _json_type(), nullable=True),
        sa.Column("companion_focus_points", _json_type(), nullable=True),
        sa.Column(
            "prompt_version_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("prompt_versions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("trace_id", sa.String(length=64), nullable=True),
        sa.Column("model", sa.String(length=64), nullable=True),
        sa.Column("estimated_cost_yuan", sa.Numeric(8, 6), nullable=True),
        sa.Column("actual_cost_yuan", sa.Numeric(8, 6), nullable=True),
        sa.Column("generation_time_ms", sa.Integer(), nullable=True),
        sa.Column("fallback_reason", sa.String(length=255), nullable=True),
        sa.Column("user_checked_items", _json_type(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_preparation_packages_order_id"),
    )
    op.create_index(
        "ix_preparation_packages_status_created_at",
        "preparation_packages",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_preparation_packages_created_at",
        "preparation_packages",
        ["created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_index(
        "ix_preparation_packages_created_at",
        table_name="preparation_packages",
    )
    op.drop_index(
        "ix_preparation_packages_status_created_at",
        table_name="preparation_packages",
    )
    op.drop_table("preparation_packages")
    op.drop_table("prompt_versions")

    if is_postgres:
        prep_status = postgresql.ENUM(
            *PREP_STATUS_VALUES,
            name="prep_status",
            create_type=False,
        )
        prep_status.drop(bind, checkfirst=True)
