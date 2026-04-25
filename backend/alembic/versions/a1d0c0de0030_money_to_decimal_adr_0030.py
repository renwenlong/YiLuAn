"""money_to_decimal_adr_0030

Revision ID: a1d0c0de0030
Revises: b2b5c0f247c3
Create Date: 2026-04-25

ADR-0030: Migrate money columns from Float (DOUBLE PRECISION) to Numeric(10, 2).

Affected columns:
  - orders.price        Float -> Numeric(10, 2)
  - payments.amount     Float -> Numeric(10, 2)

Other Float columns intentionally left unchanged:
  - hospitals.latitude / longitude   (geo, not money)
  - companions.avg_rating            (rating)
  - rate_limit timestamps (if any)

Both upgrade and downgrade preserve data via explicit USING casts on PostgreSQL.
For SQLite (used in some tests), batch_alter_table re-creates the table so
the conversion is implicit through Python-side type coercion.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a1d0c0de0030"
down_revision = "b2b5c0f247c3"
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    bind = op.get_bind()
    return bind.dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        op.alter_column(
            "orders",
            "price",
            existing_type=sa.Float(),
            type_=sa.Numeric(10, 2),
            existing_nullable=False,
            postgresql_using="price::numeric(10,2)",
        )
        op.alter_column(
            "payments",
            "amount",
            existing_type=sa.Float(),
            type_=sa.Numeric(10, 2),
            existing_nullable=False,
            postgresql_using="amount::numeric(10,2)",
        )
    else:
        # SQLite / other — batch mode recreates the table.
        with op.batch_alter_table("orders") as batch_op:
            batch_op.alter_column(
                "price",
                existing_type=sa.Float(),
                type_=sa.Numeric(10, 2),
                existing_nullable=False,
            )
        with op.batch_alter_table("payments") as batch_op:
            batch_op.alter_column(
                "amount",
                existing_type=sa.Float(),
                type_=sa.Numeric(10, 2),
                existing_nullable=False,
            )


def downgrade() -> None:
    if _is_postgres():
        op.alter_column(
            "payments",
            "amount",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Float(),
            existing_nullable=False,
            postgresql_using="amount::double precision",
        )
        op.alter_column(
            "orders",
            "price",
            existing_type=sa.Numeric(10, 2),
            type_=sa.Float(),
            existing_nullable=False,
            postgresql_using="price::double precision",
        )
    else:
        with op.batch_alter_table("payments") as batch_op:
            batch_op.alter_column(
                "amount",
                existing_type=sa.Numeric(10, 2),
                type_=sa.Float(),
                existing_nullable=False,
            )
        with op.batch_alter_table("orders") as batch_op:
            batch_op.alter_column(
                "price",
                existing_type=sa.Numeric(10, 2),
                type_=sa.Float(),
                existing_nullable=False,
            )
