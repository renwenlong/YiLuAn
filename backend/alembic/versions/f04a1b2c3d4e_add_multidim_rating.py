"""F-04: add multi-dimension rating columns to reviews

Revision ID: f04a1b2c3d4e
Revises: 79f6907afe6d
Create Date: 2026-04-25 23:55:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f04a1b2c3d4e"
down_revision: Union[str, None] = "79f6907afe6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ① 加 4 列（nullable=True，先建后回填）
    op.add_column(
        "reviews",
        sa.Column("punctuality_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "reviews",
        sa.Column("professionalism_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "reviews",
        sa.Column("communication_rating", sa.Integer(), nullable=True),
    )
    op.add_column(
        "reviews",
        sa.Column("attitude_rating", sa.Integer(), nullable=True),
    )

    # ② 数据回填：旧 row 4 维度都填同 rating 值（向后兼容）
    op.execute(
        "UPDATE reviews SET "
        "punctuality_rating = rating, "
        "professionalism_rating = rating, "
        "communication_rating = rating, "
        "attitude_rating = rating "
        "WHERE punctuality_rating IS NULL"
    )


def downgrade() -> None:
    op.drop_column("reviews", "attitude_rating")
    op.drop_column("reviews", "communication_rating")
    op.drop_column("reviews", "professionalism_rating")
    op.drop_column("reviews", "punctuality_rating")
