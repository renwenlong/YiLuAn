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
    # 幂等: 另一条分支 (b4c5d6e7f8a9 -> c5d6e7f8a9b0) 也会在 merge 前
    # 把 familiar_hospitals 改名为 service_hospitals, 故此处 add 需容错
    op.execute(
        "ALTER TABLE companion_profiles "
        "ADD COLUMN IF NOT EXISTS service_hospitals VARCHAR(1000)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE companion_profiles DROP COLUMN IF EXISTS service_hospitals"
    )
