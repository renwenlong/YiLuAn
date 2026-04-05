"""rename_familiar_hospitals_to_service_hospitals

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-04-05 23:00:00.000000
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('companion_profiles', 'familiar_hospitals', new_column_name='service_hospitals')


def downgrade() -> None:
    op.alter_column('companion_profiles', 'service_hospitals', new_column_name='familiar_hospitals')
