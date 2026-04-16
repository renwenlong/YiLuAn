"""add expires_at and new order statuses

Revision ID: f1a2b3c4d5e6
Revises: 12e9862becff
Create Date: 2026-04-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e6"
down_revision = "12e9862becff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "expires_at")
