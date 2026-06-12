"""S3-DEV-006-FOLLOWUP add admin_recommended_override to companion_profiles.

PM-005-9 第 3 条: admin 可手动 override 推荐位标识 (true/false/clear)。

字段语义 (spec v1 final §1.4 line 125-156, PR #286 `5bdadd4`):
- NULL = 未 override (走 service 默认 cert_status != uncertified 计算)
- True = admin 显式推 (sort key admin_rank=0, 上推)
- False = admin 显式压 (sort key admin_rank=2, 下压)

硬约束 (不可绕过):
即使 admin_recommended_override=True 但 cert_status=uncertified, 该陪诊师
仍被 filter_top3_recommendations 过滤掉。即数据库写入成功 (不报错) 但推荐
endpoint 仍不返回。admin override 不绕过 §1.3 cert_status 守门。

架构决策 2026-06-12 00:58Z 魈拍板方案 C、凝光 00:27Z ratify:
- 1 字段 nullable, 不新建 companion_admin_settings 表 (YAGNI)
- 不 amend ADR-0046 (题外无关)
- 已有 AdminAuditLog 表 reuse, 不新建

后续 refactor trigger: 当 admin 字段累计 ≥ 2 时再拆 companion_admin_settings 表。

Revision ID: 19e2fd967967
Revises: 557d82f796b8
Create Date: 2026-06-12 02:37:21.233379
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "19e2fd967967"
down_revision: Union[str, None] = "557d82f796b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``companion_profiles.admin_recommended_override BOOLEAN NULL``.

    All existing rows get NULL (= "未 override", 走默认计算)。
    """
    op.add_column(
        "companion_profiles",
        sa.Column(
            "admin_recommended_override",
            sa.Boolean(),
            nullable=True,
            comment="admin override 推荐位标识 (NULL=未 override, True=推, False=压); "
            "硬约束: cert_status=uncertified 即使 admin=True 也不进 top3 (spec §1.4)",
        ),
    )


def downgrade() -> None:
    """Drop ``companion_profiles.admin_recommended_override``。

    任何 admin override 数据将丢失 (本字段 nullable 默认 NULL, 大量
    生产数据应未 set, downgrade 损失最小)。
    """
    op.drop_column("companion_profiles", "admin_recommended_override")
