"""add admin_notes table

Revision ID: e1f2a3b4c5d6
Revises: f0982629bda2
Create Date: 2026-05-11 06:40:00.000000

Internal CS / ops notes attached to a (target_type, target_id) pair so the
same table can serve order ticket comments, user/companion CS flags, etc.
without bespoke per-entity tables.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, None] = "f0982629bda2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "admin_notes",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("target_type", sa.String(length=50), nullable=False),
        sa.Column("target_id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("operator", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
    )
    op.create_index(
        "ix_admin_notes_target",
        "admin_notes",
        ["target_type", "target_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_admin_notes_target", table_name="admin_notes")
    op.drop_table("admin_notes")
