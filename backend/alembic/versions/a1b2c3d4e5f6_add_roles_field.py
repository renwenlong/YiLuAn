"""add roles field

Revision ID: a1b2c3d4e5f6
Revises: bbd5bf5de583
Create Date: 2026-04-03 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bbd5bf5de583'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('roles', sa.String(length=50), nullable=True))
    # Sync existing role values to the new roles field
    op.execute("UPDATE users SET roles = role WHERE role IS NOT NULL")


def downgrade() -> None:
    op.drop_column('users', 'roles')
