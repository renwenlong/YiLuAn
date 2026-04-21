"""add expires_at to payment_callback_log [D-027]

Revision ID: 6bf94c0a3831
Revises: d9e0f1a2b3c4
Create Date: 2026-04-21 16:27:17.843233

D-027 (TTL on outbound logs):
-----------------------------
Adds a nullable, indexed ``expires_at`` column to ``payment_callback_log``.

Semantics
~~~~~~~~~
* Application layer fills ``expires_at = now() + 90 days`` on insert for
  newly-written rows. This migration does **not** backfill historical
  rows — they remain ``NULL`` and will be handled by a separate cleanup
  job under a fallback policy (e.g. "rows older than 90 days by
  ``created_at`` are eligible regardless of ``expires_at``").
* The cleanup job itself is intentionally NOT included here. It is
  tracked as TD-OPS-02 (see DECISION_LOG.md).

Scope note (A21-02-partial)
~~~~~~~~~~~~~~~~~~~~~~~~~~~
D-027 originally also covered ``sms_send_log``. That table does not
exist in the codebase yet, so the SMS half is split out as A21-02b and
will be landed once architect defines its schema (PII mask strategy /
dedupe unique constraint / write-path entry point).

Validation
~~~~~~~~~~
* SQLite ``alembic upgrade head`` / ``alembic downgrade -1`` both
  exercised locally.
* PostgreSQL: not validated on this machine, pending real-env smoke.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6bf94c0a3831"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Plain ADD COLUMN works on both PostgreSQL and SQLite for a nullable
    # column with no default. We deliberately avoid ``batch_alter_table``
    # here: on SQLite it triggers a copy-and-rebuild that drops the named
    # ``uq_payment_callback_provider_txn`` UNIQUE constraint (the
    # constraint survives but loses its name, breaking downgrade
    # symmetry and any code that references it by name).
    op.add_column(
        "payment_callback_log",
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_payment_callback_log_expires_at",
        "payment_callback_log",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_callback_log_expires_at",
        table_name="payment_callback_log",
    )
    # SQLite < 3.35 cannot DROP COLUMN, but the project's test suite
    # uses in-memory schema creation (not migrations), and prod runs on
    # PostgreSQL where DROP COLUMN is native. SQLite 3.35+ (the bundled
    # version on Python 3.12 Windows is 3.45+) also supports it.
    op.drop_column("payment_callback_log", "expires_at")
