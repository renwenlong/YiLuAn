"""add order service_name/price snapshot columns (S2-REQ-003-P3)

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-06-04 10:35:00 UTC

ADR-0043 §3 Phase 3 acceptance #3:
  Order 写入时 service_name_snapshot/service_price_snapshot 来自 service_packages 档位 + 非空

兼容老数据：先 nullable=True 加列 + 回填 (历史用 SERVICE_PRICES 硬编码 + service_type)；
后续 PR 可改 NOT NULL（现阶段保留 nullable 以免 prod 老订单回填失败崩 migration）。
"""
from typing import Union

import sqlalchemy as sa

from alembic import op

revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, None] = 'b3c4d5e6f7a8'
branch_labels = None
depends_on = None


# 硬编码 fallback 名称 (与历史 ServiceType 一致，回填用)
LEGACY_NAMES = {
    'full_accompany': '全程陪诊',
    'half_accompany': '半程陪诊',
    'errand': '跑腿代办',
}


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('service_name_snapshot', sa.String(length=100), nullable=True),
    )
    op.add_column(
        'orders',
        sa.Column('service_price_snapshot', sa.Numeric(10, 2), nullable=True),
    )

    # 回填历史数据：service_price_snapshot ← orders.price，service_name_snapshot ← legacy map
    bind = op.get_bind()
    for code, name in LEGACY_NAMES.items():
        bind.execute(
            sa.text(
                "UPDATE orders SET service_name_snapshot = :name, "
                "service_price_snapshot = price "
                "WHERE service_type = :code AND service_price_snapshot IS NULL"
            ),
            {"name": name, "code": code},
        )


def downgrade() -> None:
    op.drop_column('orders', 'service_price_snapshot')
    op.drop_column('orders', 'service_name_snapshot')
