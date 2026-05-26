"""add users.token_version for logout-all

Revision ID: d729321e2784
Revises: d058merge0001
Create Date: 2026-05-26 08:34:52.789745
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd729321e2784'
down_revision: Union[str, None] = 'd058merge0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Server-default 0 so existing rows + concurrent inserts during the
    # rollout are valid. NOT NULL because token validation does
    # ``payload['v'] == user.token_version`` on every authed request and we
    # don't want a NULL branch in the hot path.
    op.add_column(
        "users",
        sa.Column(
            "token_version",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
