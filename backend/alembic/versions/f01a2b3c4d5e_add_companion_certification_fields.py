"""add companion certification fields (F-01)

Revision ID: f01a2b3c4d5e
Revises: e8f9a0b1c2d3
Create Date: 2026-04-25 20:15:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f01a2b3c4d5e"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companion_profiles",
        sa.Column("certification_type", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "companion_profiles",
        sa.Column("certification_no", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "companion_profiles",
        sa.Column("certification_image_url", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "companion_profiles",
        sa.Column("certified_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companion_profiles", "certified_at")
    op.drop_column("companion_profiles", "certification_image_url")
    op.drop_column("companion_profiles", "certification_no")
    op.drop_column("companion_profiles", "certification_type")
    # Note: no PG enum types created in this migration; nothing to DROP TYPE.
