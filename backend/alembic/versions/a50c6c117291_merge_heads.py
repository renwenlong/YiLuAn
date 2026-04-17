"""merge msg_indexes deleted_at payment_unique heads

Revision ID: a50c6c117291
Revises: a7b8c9d0e1f2, a8b9c0d1e2f3, d6e7f8a9b0c1
Create Date: 2026-04-17 14:37:50.803538
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a50c6c117291'
down_revision: Union[str, None] = ('a7b8c9d0e1f2', 'a8b9c0d1e2f3', 'd6e7f8a9b0c1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
