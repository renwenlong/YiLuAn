"""drop redundant non-unique index ix_admin_users_username

Revision ID: a3b4c5d6e7f8
Revises: e1f2a3b4c5d6
Create Date: 2026-05-11 08:25:00.000000

The original c1d2e3f4a5b6 migration created BOTH a UNIQUE constraint
``uq_admin_users_username`` AND a non-unique btree index
``ix_admin_users_username`` on the same column. The unique constraint
already provides a usable btree index, so the standalone non-unique
one is dead weight and also caused ``alembic check`` drift after we
removed ``index=True`` from the model in this commit.

Drop the redundant index. UNIQUE constraint stays, so query plans
still get an index lookup on ``username`` — no behavior change.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a3b4c5d6e7f8"
down_revision: Union[str, None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_admin_users_username")


def downgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_admin_users_username "
        "ON admin_users (username)"
    )
