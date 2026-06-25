"""add notification_outbox table (ADR-0058 DEV-1)

Revision ID: 51e55ae91638
Revises: f01cc96aeae0
Create Date: 2026-06-25 06:33:12.947424

Notes
-----
The ``notification_outbox_status`` PG ENUM is managed explicitly (create_type=False
on the column + an explicit ``.create(checkfirst=True)`` / ``.drop(checkfirst=True)``)
following the ``6bc9f3d4a001`` (prep_status) convention. This keeps the migration
fully reversible and idempotent: a plain ``create_table`` would implicitly
``CREATE TYPE`` on upgrade but ``drop_table`` would *not* ``DROP TYPE`` on downgrade,
leaving the enum behind and breaking a re-``upgrade`` with "type already exists".
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '51e55ae91638'
down_revision: Union[str, None] = 'f01cc96aeae0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Status enum values — kept in sync with
# app.models.notification_outbox.NotificationOutboxStatus.
_OUTBOX_STATUS_VALUES = ("pending", "delivering", "delivered", "failed", "dead")
_OUTBOX_STATUS_NAME = "notification_outbox_status"


def upgrade() -> None:
    bind = op.get_bind()
    # Explicitly create the enum (idempotent) so create_type=False on the column
    # does not double-create it, and so downgrade can cleanly drop it.
    outbox_status = postgresql.ENUM(
        *_OUTBOX_STATUS_VALUES, name=_OUTBOX_STATUS_NAME, create_type=False
    )
    outbox_status.create(bind, checkfirst=True)

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_dedup_key", sa.String(length=255), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(
                postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                *_OUTBOX_STATUS_VALUES,
                name=_OUTBOX_STATUS_NAME,
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_dedup_key"),
    )
    op.create_index(
        "ix_notification_outbox_status_next_retry",
        "notification_outbox",
        ["status", "next_retry_at"],
        unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_index(
        "ix_notification_outbox_status_next_retry",
        table_name="notification_outbox",
    )
    op.drop_table("notification_outbox")
    # drop_table does not drop the PG enum type — do it explicitly (idempotent).
    outbox_status = postgresql.ENUM(
        *_OUTBOX_STATUS_VALUES, name=_OUTBOX_STATUS_NAME, create_type=False
    )
    outbox_status.drop(bind, checkfirst=True)
