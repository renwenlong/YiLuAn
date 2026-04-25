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
    # 幂等：另一分支 12e9862becff 可能已经 ADD COLUMN IF NOT EXISTS 了
    # service_hospitals。此时不需再 rename；仅在 familiar_hospitals 还存在时 rename。
    op.execute(
        "DO $$\n"
        "BEGIN\n"
        "  IF EXISTS (\n"
        "    SELECT 1 FROM information_schema.columns\n"
        "    WHERE table_name = 'companion_profiles'\n"
        "      AND column_name = 'familiar_hospitals'\n"
        "  ) THEN\n"
        "    ALTER TABLE companion_profiles\n"
        "      RENAME familiar_hospitals TO service_hospitals;\n"
        "  END IF;\n"
        "END$$"
    )


def downgrade() -> None:
    # 幂等：双头合流后另一分支 (12e9862becff) 的 downgrade 可能已先一步
    # DROP 了 service_hospitals；此时 rename 会报列不存在。
    # 使用 DO block 在列存在时才 rename。
    op.execute(
        "DO $$\n"
        "BEGIN\n"
        "  IF EXISTS (\n"
        "    SELECT 1 FROM information_schema.columns\n"
        "    WHERE table_name = 'companion_profiles'\n"
        "      AND column_name = 'service_hospitals'\n"
        "  ) THEN\n"
        "    ALTER TABLE companion_profiles\n"
        "      RENAME service_hospitals TO familiar_hospitals;\n"
        "  END IF;\n"
        "END$$"
    )
