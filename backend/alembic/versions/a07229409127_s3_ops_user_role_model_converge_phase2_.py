"""S3-OPS-USER-ROLE-MODEL-CONVERGE-PHASE2-IMPL backfill roles from role enum (ADR-0055)

Revision ID: a07229409127
Revises: cd47cb5f8a1c
Create Date: 2026-06-15 10:55:43.832794

ADR-0055 §3.2 Phase 2 backfill:

Users with legacy ``role`` enum set (e.g. ``role='patient'``) but missing
multi-role ``roles`` string (NULL) would lose access under the new single-
SoT model where ``has_role()`` reads exclusively from ``roles``. This
idempotent UPDATE copies enum value into the string field for any such row.

Idempotent: re-running has no effect because the WHERE clause only matches
rows where ``roles IS NULL``. Once backfilled, the row no longer qualifies.

No-op for new users created after this migration: auth.py + companion_profile
write ``roles`` directly, so they never reach the NULL state.

Not reversible: downgrade is a no-op because once ``roles`` is set, we
cannot tell whether it was populated by this migration or written natively
by app code; reverting would risk data loss.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a07229409127'
down_revision: Union[str, None] = 'cd47cb5f8a1c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ADR-0055 §3.2: idempotent backfill of multi-role string from legacy
    # enum field. Only touches rows where roles is NULL AND role is set,
    # so repeated runs are no-ops. SQLite stores enum as text natively;
    # PostgreSQL performs implicit enum -> text cast in this assignment
    # context (same pattern as the original sync migration a1b2c3d4e5f6).
    op.execute(
        "UPDATE users "
        "SET roles = role "
        "WHERE role IS NOT NULL AND roles IS NULL"
    )


def downgrade() -> None:
    # No-op: once roles is populated we cannot distinguish backfilled rows
    # from natively-written rows, and reverting could discard data added by
    # app code (e.g. multi-role users with patient,companion).
    pass
