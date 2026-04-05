"""add service_hospitals column to companion_profiles

Revision ID: 12e9862becff
Revises: f3a7b8c9d0e1
Create Date: 2026-04-05 14:44:12.896036
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '12e9862becff'
down_revision: Union[str, None] = 'f3a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companion_profiles', sa.Column('service_hospitals', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('companion_profiles', 'service_hospitals')
