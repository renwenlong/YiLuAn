"""D-058 add idempotency_keys + payments.sign_params_cache

Revision ID: c7d8e9f0a1b2
Revises: b5c6d7e8f9a0
Create Date: 2026-05-25 00:00:00.000000

Adds two pieces of infra for order/payment idempotency hardening
(see ``docs/decisions/D-058-order-idempotency.md``):

1. ``idempotency_keys`` table — replay cache for client-supplied
   ``Idempotency-Key`` HTTP header. Initial consumer is
   ``POST /api/v1/orders``.

2. ``payments.sign_params_cache`` column — cached JSON of the prepay
   signing payload so retries on a ``pending`` payment can return the
   same params without re-hitting the PSP.

Both changes use vanilla Core constructs (``op.create_table``,
``op.add_column``) so they apply cleanly to PostgreSQL and SQLite
without dialect specialisation.

PG smoke: validated locally against ``yiluan_smoke`` (upgrade /
downgrade -1 / upgrade head all clean).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- idempotency_keys -------------------------------------------------
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("endpoint", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
            index=True,
        ),
        sa.UniqueConstraint(
            "user_id",
            "endpoint",
            "key",
            name="uq_idempotency_user_endpoint_key",
        ),
    )
    # Indexes on user_id / expires_at are declared inline via ``index=True``
    # above (mirroring the SQLAlchemy model). We deliberately do NOT also
    # call ``op.create_index`` for them — mixing ``Column(index=True)`` with
    # ``op.create_index`` on the same column causes PG ``DuplicateTable``
    # on the second upgrade (see memory note 2026-05-19 / F-05 lesson).
    # ``alembic check`` keeps model metadata and migration in sync this way.

    # --- payments.sign_params_cache --------------------------------------
    op.add_column(
        "payments",
        sa.Column("sign_params_cache", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payments", "sign_params_cache")
    # Inline indexes are dropped automatically by ``drop_table`` on both
    # PG and SQLite, so no explicit ``drop_index`` calls are needed.
    op.drop_table("idempotency_keys")
