"""S2-REQ-003-P1: add service_packages table + seed 3 historical types

Replaces hardcoded ServiceType Enum + SERVICE_PRICES dict (ADR-0043 §2.1).
- service_packages table with code/name/price/is_active/sort_order/audit fields
- seed 3 historical types: full_accompany / half_accompany / errand
  (sort 10/20/30 leaves gaps for future insertions)
- price uses Decimal(10,2) per ADR-0030

Order.service_type weakly references service_packages.code (no FK constraint,
per ADR-0043 §2.2 to avoid cascade complexity).

Revision ID: b3c4d5e6f7a8
Revises: f7a8b9c0d1e2
Create Date: 2026-06-04 04:00:00.000000
"""
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = 'b3c4d5e6f7a8'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ----- create service_packages table -----
    op.create_table(
        "service_packages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.String(500), nullable=True),
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
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_service_packages_code", "service_packages", ["code"], unique=True
    )

    # ----- seed 3 historical types (与 ServiceType Enum + SERVICE_PRICES 一致) -----
    # 用 op.bulk_insert 避免 ORM 在迁移中的 import cycle 风险
    import uuid as _uuid
    from datetime import datetime
    from datetime import timezone as _tz

    now = datetime.now(_tz.utc)
    service_packages = sa.table(
        "service_packages",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("price", sa.Numeric(10, 2)),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("description", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        service_packages,
        [
            {
                "id": _uuid.uuid4(),
                "code": "full_accompany",
                "name": "全程陪诊",
                "price": Decimal("299.00"),
                "is_active": True,
                "sort_order": 10,
                "description": "全程陪诊服务 (含挂号/取药/全程陪同)",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid.uuid4(),
                "code": "half_accompany",
                "name": "半程陪诊",
                "price": Decimal("199.00"),
                "is_active": True,
                "sort_order": 20,
                "description": "半程陪诊服务 (含挂号/部分陪同)",
                "created_at": now,
                "updated_at": now,
            },
            {
                "id": _uuid.uuid4(),
                "code": "errand",
                "name": "代办跑腿",
                "price": Decimal("149.00"),
                "is_active": True,
                "sort_order": 30,
                "description": "代办取药 / 代办挂号 等单项服务",
                "created_at": now,
                "updated_at": now,
            },
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_service_packages_code", table_name="service_packages")
    op.drop_table("service_packages")
