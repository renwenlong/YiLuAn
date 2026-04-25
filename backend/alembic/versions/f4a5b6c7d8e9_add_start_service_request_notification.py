"""add start_service_request to notificationtype enum

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-04-05 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f4a5b6c7d8e9'
down_revision: Union[str, None] = 'e3f4a5b6c7d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum values prior to this migration (used by downgrade to rebuild the type).
_OLD_ENUM_VALUES = (
    "order_status_changed",
    "new_message",
    "new_order",
    "review_received",
    "system",
)
_NEW_VALUE = "start_service_request"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # ADD VALUE must run outside a transaction in older PG versions; alembic
        # in offline/online mode handles this with autocommit_block when needed.
        op.execute(
            f"ALTER TYPE notificationtype ADD VALUE IF NOT EXISTS '{_NEW_VALUE}'"
        )
    # On SQLite/other dialects the enum is enforced at the Python layer, so
    # nothing to do at the DB level.


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # No-op for sqlite/other dialects (enum enforced in Python only).
        return

    # PostgreSQL does not support `ALTER TYPE ... DROP VALUE`, so we rebuild
    # the enum without the new value. Idempotent: if `notificationtype_old`
    # exists from a previous failed downgrade, drop it first.
    quoted_values = ", ".join(f"'{v}'" for v in _OLD_ENUM_VALUES)

    op.execute("DROP TYPE IF EXISTS notificationtype_old")

    # First, rewrite any rows that reference the value being removed so the
    # USING cast below does not fail. Map them to a safe fallback.
    op.execute(
        "UPDATE notifications SET type = 'system' "
        f"WHERE type::text = '{_NEW_VALUE}'"
    )

    op.execute("ALTER TYPE notificationtype RENAME TO notificationtype_old")
    op.execute(f"CREATE TYPE notificationtype AS ENUM ({quoted_values})")
    op.execute(
        "ALTER TABLE notifications "
        "ALTER COLUMN type TYPE notificationtype "
        "USING type::text::notificationtype"
    )
    op.execute("DROP TYPE notificationtype_old")
