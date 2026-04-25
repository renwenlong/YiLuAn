"""[F-02] add target_type/target_id to notifications (deep-link navigation)

Revision ID: f02a1b2c3d4e
Revises: e8f9a0b1c2d3
Create Date: 2026-04-25 20:30:00.000000

加入 ``target_type`` (enum: order/companion/system/payment/review) 和
``target_id`` (string, nullable)，供小程序 / iOS 通知列表深链跳转使用。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f02a1b2c3d4e"
down_revision: Union[str, None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TARGET_TYPE_VALUES = ("order", "companion", "system", "payment", "review")
_ENUM_NAME = "notificationtargettype"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # 在 PG 上需要先显式创建 ENUM 类型，再 add column 引用它。
        op.execute(
            "DO $$ BEGIN "
            f"CREATE TYPE {_ENUM_NAME} AS ENUM ("
            + ", ".join(f"'{v}'" for v in _TARGET_TYPE_VALUES)
            + "); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$;"
        )
        target_type_col = sa.Column(
            "target_type",
            sa.Enum(*_TARGET_TYPE_VALUES, name=_ENUM_NAME, create_type=False),
            nullable=True,
        )
    else:
        # SQLite 等方言下 SQLAlchemy 会把 Enum 退化成 VARCHAR + CHECK。
        target_type_col = sa.Column(
            "target_type",
            sa.Enum(*_TARGET_TYPE_VALUES, name=_ENUM_NAME),
            nullable=True,
        )

    op.add_column("notifications", target_type_col)
    op.add_column(
        "notifications",
        sa.Column("target_id", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_column("notifications", "target_id")
    op.drop_column("notifications", "target_type")

    if bind.dialect.name == "postgresql":
        # PG 下显式 DROP TYPE，避免遗留孤儿 enum 类型。
        op.execute(f"DROP TYPE IF EXISTS {_ENUM_NAME}")
