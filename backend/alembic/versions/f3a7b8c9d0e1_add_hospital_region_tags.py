"""add hospital region and tags fields

Revision ID: f3a7b8c9d0e1
Revises: 2efb4290575a
Create Date: 2026-04-05 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a7b8c9d0e1'
down_revision: Union[str, None] = '2efb4290575a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('hospitals', sa.Column('province', sa.String(length=50), nullable=True))
    op.add_column('hospitals', sa.Column('city', sa.String(length=50), nullable=True))
    op.add_column('hospitals', sa.Column('district', sa.String(length=50), nullable=True))
    op.add_column('hospitals', sa.Column('tags', sa.String(length=500), nullable=True))
    op.create_index(op.f('ix_hospitals_province'), 'hospitals', ['province'], unique=False)
    op.create_index(op.f('ix_hospitals_city'), 'hospitals', ['city'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hospitals_city'), table_name='hospitals')
    op.drop_index(op.f('ix_hospitals_province'), table_name='hospitals')
    op.drop_column('hospitals', 'tags')
    op.drop_column('hospitals', 'district')
    op.drop_column('hospitals', 'city')
    op.drop_column('hospitals', 'province')
