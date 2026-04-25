"""[F-03] add emergency_contacts and emergency_events tables

Revision ID: f03e0001a1b2
Revises: 79f6907afe6d
Create Date: 2026-04-25 23:50:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f03e0001a1b2"
down_revision: Union[str, None] = "79f6907afe6d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "emergency_contacts",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=False),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_emergency_contacts_user_id",
        "emergency_contacts",
        ["user_id"],
    )

    op.create_table(
        "emergency_events",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "patient_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "order_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orders.id"),
            nullable=True,
        ),
        sa.Column("contact_called", sa.String(length=50), nullable=False),
        sa.Column("contact_type", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_emergency_events_patient_id",
        "emergency_events",
        ["patient_id"],
    )
    op.create_index(
        "ix_emergency_events_order_id",
        "emergency_events",
        ["order_id"],
    )
    op.create_index(
        "ix_emergency_events_triggered_at",
        "emergency_events",
        ["triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_emergency_events_triggered_at", table_name="emergency_events")
    op.drop_index("ix_emergency_events_order_id", table_name="emergency_events")
    op.drop_index("ix_emergency_events_patient_id", table_name="emergency_events")
    op.drop_table("emergency_events")
    op.drop_index("ix_emergency_contacts_user_id", table_name="emergency_contacts")
    op.drop_table("emergency_contacts")
