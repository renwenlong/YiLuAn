"""merge f01 companion certification + f02 notification deeplink heads

Revision ID: 79f6907afe6d
Revises: f01a2b3c4d5e, f02a1b2c3d4e
Create Date: 2026-04-25 23:30:13.056211
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '79f6907afe6d'
down_revision: Union[str, None] = ('f01a2b3c4d5e', 'f02a1b2c3d4e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
