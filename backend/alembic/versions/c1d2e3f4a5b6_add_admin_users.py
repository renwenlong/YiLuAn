"""[B2 / ADR-0034] add admin_users table + seed initial super account

Revision ID: c1d2e3f4a5b6
Revises: b1d0d4e51b00
Create Date: 2026-05-04 10:30:00.000000

Adds the operator entity table backing Admin v2 (JWT auth + audit traceability).
Seeds a single ``super`` account so dev/staging deployments work out of the box;
prod must rotate this password via runbook before exposing the login endpoint.
"""

from datetime import datetime, timezone
from typing import Sequence, Union

import bcrypt
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "b1d0d4e51b00"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_ROLE_VALUES = ("super", "ops", "finance")
_ENUM_NAME = "admin_role"


def _make_enum() -> sa.types.TypeEngine:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Use postgresql.ENUM (not sa.Enum) so create_type=False is honored
        # by SQLAlchemy's _on_table_create hook. Pre-create the type guarded
        # by EXCEPTION WHEN duplicate_object so a partial prior run is safe.
        op.execute(
            "DO $$ BEGIN "
            f"CREATE TYPE {_ENUM_NAME} AS ENUM ("
            + ", ".join(f"'{v}'" for v in _ROLE_VALUES)
            + "); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        return postgresql.ENUM(
            *_ROLE_VALUES, name=_ENUM_NAME, create_type=False
        )
    return sa.Enum(*_ROLE_VALUES, name=_ENUM_NAME)


def upgrade() -> None:
    role_enum = _make_enum()

    op.create_table(
        "admin_users",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column("username", sa.String(length=64), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", role_enum, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("username", name="uq_admin_users_username"),
    )
    op.create_index(
        "ix_admin_users_username", "admin_users", ["username"], unique=False
    )

    # Seed: single super account. Password is the dev/staging default
    # documented in ADR-0034; prod rotates via runbook before exposing /admin/login.
    seed_password = "Admin@2026!"
    seed_hash = bcrypt.hashpw(seed_password.encode("utf-8"), bcrypt.gensalt(rounds=12))
    op.execute(
        sa.text(
            "INSERT INTO admin_users "
            "(username, password_hash, role, is_active, created_at) "
            "VALUES (:u, :h, CAST(:r AS admin_role), :a, :ts)"
            if op.get_bind().dialect.name == "postgresql"
            else "INSERT INTO admin_users "
            "(username, password_hash, role, is_active, created_at) "
            "VALUES (:u, :h, :r, :a, :ts)"
        ).bindparams(
            sa.bindparam("u", "admin"),
            sa.bindparam("h", seed_hash.decode("utf-8")),
            sa.bindparam("r", "super"),
            sa.bindparam("a", True),
            sa.bindparam("ts", datetime.now(timezone.utc)),
        )
    )


def downgrade() -> None:
    op.drop_index("ix_admin_users_username", table_name="admin_users")
    op.drop_table("admin_users")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(f"DROP TYPE IF EXISTS {_ENUM_NAME}")
