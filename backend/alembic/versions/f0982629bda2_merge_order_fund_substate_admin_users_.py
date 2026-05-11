"""merge order fund substate + admin_users heads

Revision ID: f0982629bda2
Revises: a1b2c3d4e5f7, c1d2e3f4a5b6
Create Date: 2026-05-11 04:19:16.975540
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0982629bda2'
down_revision: Union[str, None] = ('a1b2c3d4e5f7', 'c1d2e3f4a5b6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
