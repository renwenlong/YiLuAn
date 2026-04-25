"""merge f03 emergency + f04 multidim rating heads

Revision ID: b2b5c0f247c3
Revises: f03e0001a1b2, f04a1b2c3d4e
Create Date: 2026-04-26 00:07:13.329907
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2b5c0f247c3'
down_revision: Union[str, None] = ('f03e0001a1b2', 'f04a1b2c3d4e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
