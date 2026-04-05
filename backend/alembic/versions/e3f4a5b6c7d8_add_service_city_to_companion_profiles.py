"""add service_city to companion_profiles

Revision ID: e3f4a5b6c7d8
Revises: 12e9862becff
Create Date: 2026-04-05 15:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3f4a5b6c7d8'
down_revision: Union[str, None] = '12e9862becff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companion_profiles', sa.Column('service_city', sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column('companion_profiles', 'service_city')
