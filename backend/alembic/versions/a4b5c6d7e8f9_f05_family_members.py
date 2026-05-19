"""F-05: add family_members table + denormalized family snapshot columns on orders

Revision ID: a4b5c6d7e8f9
Revises: a3b4c5d6e7f8
Create Date: 2026-05-19 03:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "a3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FAMILY_RELATION_VALUES = (
    "self",
    "parent",
    "spouse",
    "child",
    "sibling",
    "grandparent",
    "relative",
    "friend",
    "other",
)
FAMILY_GENDER_VALUES = ("unknown", "male", "female")


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    if dialect == "postgresql":
        # Step 1: create the enum types first (checkfirst keeps re-upgrade safe).
        sa.Enum(*FAMILY_RELATION_VALUES, name="familyrelation").create(
            bind, checkfirst=True
        )
        sa.Enum(*FAMILY_GENDER_VALUES, name="familygender").create(
            bind, checkfirst=True
        )
        # Step 2: bind columns to the existing type, but tell SQLAlchemy
        # NOT to re-emit CREATE TYPE inside create_table (otherwise repeat
        # upgrade after downgrade => 42710 already exists).
        relation_type = postgresql.ENUM(
            *FAMILY_RELATION_VALUES, name="familyrelation", create_type=False
        )
        gender_type = postgresql.ENUM(
            *FAMILY_GENDER_VALUES, name="familygender", create_type=False
        )
    else:
        relation_type = sa.Enum(*FAMILY_RELATION_VALUES, name="familyrelation")
        gender_type = sa.Enum(*FAMILY_GENDER_VALUES, name="familygender")

    op.create_table(
        "family_members",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column(
            "relation", relation_type, nullable=False, server_default="other"
        ),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column(
            "gender", gender_type, nullable=False, server_default="unknown"
        ),
        sa.Column("age", sa.Integer(), nullable=True),
        sa.Column("medical_notes", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_family_members_user_id", "family_members", ["user_id"]
    )
    op.create_index(
        "ix_family_members_deleted_at", "family_members", ["deleted_at"]
    )

    # F-05: denormalized snapshot on orders so historical orders survive
    # a family-member soft delete.
    op.add_column(
        "orders",
        sa.Column("family_member_id", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("family_member_name", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("family_member_relation", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("family_member_phone", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_orders_family_member_id", "orders", ["family_member_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_orders_family_member_id", table_name="orders")
    op.drop_column("orders", "family_member_phone")
    op.drop_column("orders", "family_member_relation")
    op.drop_column("orders", "family_member_name")
    op.drop_column("orders", "family_member_id")

    op.drop_index("ix_family_members_deleted_at", table_name="family_members")
    op.drop_index("ix_family_members_user_id", table_name="family_members")
    op.drop_table("family_members")

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        sa.Enum(name="familygender").drop(bind, checkfirst=True)
        sa.Enum(name="familyrelation").drop(bind, checkfirst=True)
