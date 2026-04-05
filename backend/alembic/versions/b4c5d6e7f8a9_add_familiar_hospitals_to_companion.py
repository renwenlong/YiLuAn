"""add_familiar_hospitals_to_companion_profile

Revision ID: b4c5d6e7f8a9
Revises: f3a7b8c9d0e1
Create Date: 2026-04-05 22:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, None] = 'f3a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companion_profiles', sa.Column('familiar_hospitals', sa.String(length=1000), nullable=True))


def downgrade() -> None:
    op.drop_column('companion_profiles', 'familiar_hospitals')
