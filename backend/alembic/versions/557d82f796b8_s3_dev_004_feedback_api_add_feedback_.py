"""S3-DEV-004-FEEDBACK-API add feedback_attachments table (architect ratify scope merge)

ADR-0049 §5.2 完整 schema, 10 列 + 1 index + 1 CHECK.

# Architect ratify D (2026-06-11)

ADR-0049 §8 implementation map originally assigned ``feedback_attachments``
migration to S3-DEV-004-FEEDBACK-DOMAIN task, but that task's acceptance
criteria only listed ``user_feedbacks`` (4 ACs, no attachment row).
FEEDBACK-DOMAIN shipped per-AC compliant; the attachment table fell
through architect-side task scope drift. Architect 魈 explicit ratify
on 2026-06-11: scope merged into S3-DEV-004-FEEDBACK-API (this PR).
AC#0 (6th acceptance criterion) of the FEEDBACK-API task now requires
this migration.

# Downgrade caveat

drop_table 自动 drop index; CHECK constraint is column-level, dropped
with the table. No additional ENUM types are introduced (FK columns
reuse existing types).

Revision ID: 557d82f796b8
Revises: fc921567741d
Create Date: 2026-06-11 09:19:50.294840
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "557d82f796b8"
down_revision: Union[str, None] = "fc921567741d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "feedback_attachments",
        sa.Column(
            "id",
            sa.Uuid(),
            nullable=False,
            comment="附件行 PK (gen_random_uuid)",
        ),
        sa.Column(
            "feedback_id",
            sa.Uuid(),
            nullable=False,
            comment="所属反馈 FK (ON DELETE CASCADE)",
        ),
        sa.Column(
            "storage_uri",
            sa.Text(),
            nullable=False,
            comment=(
                "StorageBackend uri (local:// / azure://); "
                "never user-controlled path"
            ),
        ),
        sa.Column(
            "content_type",
            sa.String(length=128),
            nullable=False,
            comment=(
                "MIME (allowlist enforced upstream in "
                "feedback_attachment_storage)"
            ),
        ),
        sa.Column(
            "byte_size",
            sa.Integer(),
            nullable=False,
            comment="字节数 (上层 10 MiB cap)",
        ),
        sa.Column(
            "content_hash",
            sa.CHAR(length=64),
            nullable=False,
            comment=(
                "SHA-256 全 64 字符 hex (idempotency / tamper-evident)"
            ),
        ),
        sa.Column(
            "uploaded_by_user_id",
            sa.Uuid(),
            nullable=True,
            comment="用户上传方 (XOR admin, CHECK chk_uploaded_by)",
        ),
        sa.Column(
            "uploaded_by_admin_id",
            sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
            nullable=True,
            comment="admin 代上传方 (XOR user, CHECK chk_uploaded_by)",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="行创建时间 (immutable)",
        ),
        sa.CheckConstraint(
            "(uploaded_by_user_id IS NOT NULL "
            "AND uploaded_by_admin_id IS NULL) "
            "OR "
            "(uploaded_by_user_id IS NULL "
            "AND uploaded_by_admin_id IS NOT NULL)",
            name="chk_uploaded_by",
        ),
        sa.ForeignKeyConstraint(
            ["feedback_id"], ["user_feedbacks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_admin_id"], ["admin_users.id"]
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by_user_id"], ["users.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_feedback_attachments_feedback_id",
        "feedback_attachments",
        ["feedback_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_feedback_attachments_feedback_id",
        table_name="feedback_attachments",
    )
    op.drop_table("feedback_attachments")
