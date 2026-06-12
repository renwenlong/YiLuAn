"""S2-DEV-016 users add is_read_only + read_only_reason_category + read_only_set_at + read_only_set_by.

S2-DEV-016-READ-ONLY-FLAG-DB (ADR-0053 §5.1).

Schema (ratified 魈 08:08Z PR #295 `2566a02` after ADR §5 evidence typo fix):

    ALTER TABLE users
        ADD COLUMN is_read_only BOOLEAN NOT NULL DEFAULT FALSE,
        ADD COLUMN read_only_reason_category VARCHAR(32) NULL,
        ADD COLUMN read_only_set_at TIMESTAMPTZ NULL,
        ADD COLUMN read_only_set_by INT NULL REFERENCES admin_users(id) ON DELETE SET NULL;

    CREATE INDEX ix_users_is_read_only ON users (is_read_only)
        WHERE is_read_only = TRUE;  -- partial index per ADR-0053 §5.1

Reason column design (single-column, ratify via AdminAuditLog re-use):

    - ``read_only_reason_category`` (VARCHAR(32)) — UX enum returned to frontend
      per PRD-001 §F8 D2 (GRAY_REVOKE / GRAY_ANOMALY / CREDENTIAL_LEAK /
      COMPLIANCE_REPORT). NULL when ``is_read_only = FALSE``.
    - Free-text admin ``reason_detail`` (not user-facing) stored in
      ``admin_audit_logs.reason`` (existing TEXT NULL column) per S2-OPS-A-
      READ-ONLY-FLAG-ADMIN-API AC#4 — *not* a new column on ``users``.

FK target = ``admin_users.id`` (BigInt PG / Int SQLite), not ``users.id``:

    - business semantics = admin operation (admin set the flag, not the user)
    - AC#1 字面 typo (REFERENCES users(id) + INT) — UUID/INT type mismatch
      against ``users.id``. ratify 魈 08:08Z → ``admin_users(id)`` (INT match).
    - ADR-0053 §5 字面 (UUID + admins) was also wrong — fixed by ADR amend
      PR #295.

ON DELETE SET NULL: when an admin row is deleted (rare), preserve the read-only
history fields (``read_only_set_at``, ``read_only_reason_category``,
``is_read_only``) for audit/forensics; only the FK link is cleared.

Partial index ``ix_users_is_read_only WHERE is_read_only = TRUE``: read-only
users are the small minority (<<1% expected); partial index keeps the planner
overhead off the 99.9% normal-write users while still giving O(log n) admin
scans of the read-only cohort.

Revision ID: cd47cb5f8a1c
Revises: 19e2fd967967
Create Date: 2026-06-12 08:16:35.288770
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "cd47cb5f8a1c"
down_revision: Union[str, None] = "19e2fd967967"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the 4 read-only flag columns + partial index + FK on ``users``."""
    op.add_column(
        "users",
        sa.Column(
            "is_read_only",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment=(
                "read-only mode flag; TRUE → mutating endpoints (POST/PUT/DELETE)"
                " return 403 USER_READONLY. ADR-0053 §5.1."
            ),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "read_only_reason_category",
            sa.String(length=32),
            nullable=True,
            comment=(
                "UX category mapped by frontend per PRD-001 §F8 D2"
                " (GRAY_REVOKE / GRAY_ANOMALY / CREDENTIAL_LEAK / COMPLIANCE_REPORT)."
                " NULL when is_read_only=FALSE."
            ),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "read_only_set_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="UTC timestamp when an admin most recently flipped is_read_only=TRUE.",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "read_only_set_by",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
            comment=(
                "FK → admin_users.id; admin who last toggled is_read_only=TRUE."
                " NULL after the admin row is deleted (ON DELETE SET NULL)."
            ),
        ),
    )
    op.create_index(
        "ix_users_is_read_only",
        "users",
        ["is_read_only"],
        unique=False,
        postgresql_where="is_read_only = TRUE",
    )
    op.create_foreign_key(
        "fk_users_read_only_set_by_admin_users",
        "users",
        "admin_users",
        ["read_only_set_by"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Drop the FK, index, and 4 columns in reverse order.

    Any read-only flag rows are lost on downgrade; this is acceptable for
    a feature-rollback scenario (admin can re-mark from audit_log history).
    """
    op.drop_constraint(
        "fk_users_read_only_set_by_admin_users", "users", type_="foreignkey"
    )
    op.drop_index(
        "ix_users_is_read_only",
        table_name="users",
        postgresql_where="is_read_only = TRUE",
    )
    op.drop_column("users", "read_only_set_by")
    op.drop_column("users", "read_only_set_at")
    op.drop_column("users", "read_only_reason_category")
    op.drop_column("users", "is_read_only")
