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
    # 幂等：合流后另一分支 12e9862becff 也会 ADD COLUMN IF NOT EXISTS
    # service_hospitals，随后 c5d6e7f8a9b0 会 rename familiar -> service。
    # 在重复 upgrade 场景中 familiar_hospitals 可能已被重命名；仅在
    # familiar_hospitals 不存在且 service_hospitals 也不存在时才创建。
    op.execute(
        "DO $$\n"
        "BEGIN\n"
        "  IF NOT EXISTS (\n"
        "    SELECT 1 FROM information_schema.columns\n"
        "    WHERE table_name = 'companion_profiles'\n"
        "      AND column_name IN ('familiar_hospitals', 'service_hospitals')\n"
        "  ) THEN\n"
        "    ALTER TABLE companion_profiles\n"
        "      ADD COLUMN familiar_hospitals VARCHAR(1000);\n"
        "  END IF;\n"
        "END$$"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE companion_profiles "
        "DROP COLUMN IF EXISTS familiar_hospitals"
    )
