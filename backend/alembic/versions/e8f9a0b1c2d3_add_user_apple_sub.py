"""add apple_sub column to users (Apple Sign-In)

Revision ID: e8f9a0b1c2d3
Revises: d1e2f3a4b5c6
Create Date: 2026-04-24 23:15:00.000000

[W18-A] Apple Sign-In support: stable Apple user identifier (`sub` claim).
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("apple_sub", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_users_apple_sub",
        "users",
        ["apple_sub"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_users_apple_sub", table_name="users")
    op.drop_column("users", "apple_sub")
