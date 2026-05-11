"""add payment_state and refund_state sub-state columns to orders

Revision ID: a1b2c3d4e5f7
Revises: b1d0d4e51b00
Create Date: 2026-05-04 11:00:00.000000

H2-be / ADR-0035 (lite). Sub-states are independent of OrderStatus and let
the UI surface fund-side situations (refund pending, refund failed, manual
review) without polluting the business state machine.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f7"
down_revision = "b1d0d4e51b00"
branch_labels = None
depends_on = None


PAYMENT_STATES = ("none", "paying", "paid", "failed", "abnormal")
REFUND_STATES = ("none", "refunding", "refunded", "failed", "manual_review")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        sa.Enum(*PAYMENT_STATES, name="paymentstate").create(bind, checkfirst=True)
        sa.Enum(*REFUND_STATES, name="refundstate").create(bind, checkfirst=True)
        # Use postgresql.ENUM with create_type=False so add_column does not
        # try to re-create the type via the _on_table_create hook.
        payment_state = postgresql.ENUM(
            *PAYMENT_STATES, name="paymentstate", create_type=False
        )
        refund_state = postgresql.ENUM(
            *REFUND_STATES, name="refundstate", create_type=False
        )
    else:
        # SQLite/MySQL store enums as VARCHAR-with-CHECK; emit plain Enum.
        payment_state = sa.Enum(*PAYMENT_STATES, name="paymentstate")
        refund_state = sa.Enum(*REFUND_STATES, name="refundstate")

    with op.batch_alter_table("orders") as batch:
        batch.add_column(
            sa.Column(
                "payment_state",
                payment_state,
                nullable=False,
                server_default="none",
            )
        )
        batch.add_column(
            sa.Column(
                "refund_state",
                refund_state,
                nullable=False,
                server_default="none",
            )
        )

    op.create_index(
        "ix_orders_payment_state", "orders", ["payment_state"], unique=False
    )
    op.create_index(
        "ix_orders_refund_state", "orders", ["refund_state"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_orders_refund_state", table_name="orders")
    op.drop_index("ix_orders_payment_state", table_name="orders")
    with op.batch_alter_table("orders") as batch:
        batch.drop_column("refund_state")
        batch.drop_column("payment_state")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="refundstate").drop(bind, checkfirst=True)
        sa.Enum(name="paymentstate").drop(bind, checkfirst=True)
