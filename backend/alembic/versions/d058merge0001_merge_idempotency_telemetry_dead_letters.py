"""merge idempotency_keys into telemetry/dead_letters chain

Revision ID: d058merge0001
Revises: c7d8e9f0a1b2, d2e3f4a5b6c8
Create Date: 2026-05-25 15:00:00.000000

After the c1d2e3f4a5b7 rename fix on main (PR #94), the migration chain
under b5c6d7e8f9a0 looks like:

    b5c6d7e8f9a0 (followup_reminders)
      ├─ c1d2e3f4a5b7 (dead_letters) → d2e3f4a5b6c8 (telemetry_events)
      └─ c7d8e9f0a1b2 (D-058 idempotency_keys + payments.sign_params_cache)

This no-op merge revision collapses those two heads back into a single
linear chain so ``alembic upgrade head`` resolves cleanly.
"""
from typing import Sequence, Union


revision: str = "d058merge0001"
down_revision: Union[str, Sequence[str], None] = (
    "c7d8e9f0a1b2",
    "d2e3f4a5b6c8",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
