"""FeedbackAttachment ORM model (S3-DEV-004-FEEDBACK-API / ADR-0049 §5.2).

# Scope merge note (architect ratify D, 2026-06-11)

ADR-0049 §8 implementation map originally assigned ``feedback_attachments``
migration to **S3-DEV-004-FEEDBACK-DOMAIN** task, but that task's acceptance
criteria only listed ``user_feedbacks`` (4 ACs, no attachment row). FEEDBACK-DOMAIN
shipped per-AC compliant; the attachment table fell through architect-side
task scope drift (魈 ratify case #10).

魈 (architect) explicit ratify on 2026-06-11: scope merged into
S3-DEV-004-FEEDBACK-API (this task). AC#0 (6th acceptance criterion) now
explicitly requires this model + companion migration + service helper.

# Schema (ADR-0049 §5.2 1:1)

10 columns + 1 index + 1 CHECK constraint:

| Column                   | Type            | Note                              |
|--------------------------|-----------------|-----------------------------------|
| id                       | UUID PK         | gen_random_uuid()                 |
| feedback_id              | UUID NOT NULL   | FK user_feedbacks(id) ON DELETE CASCADE |
| storage_uri              | TEXT NOT NULL   | StorageBackend uri (e.g. local://…/feedback/…) |
| content_type             | VARCHAR(128)    | allowlist enforced upstream       |
| byte_size                | INTEGER         | upstream 10 MiB cap               |
| content_hash             | CHAR(64)        | SHA-256 hex (idempotency)         |
| uploaded_by_user_id      | UUID NULL       | FK users(id)                      |
| uploaded_by_admin_id     | BigInt NULL     | FK admin_users(id)                |
| created_at               | TIMESTAMPTZ     | default now()                     |
| chk_uploaded_by          | CHECK           | exactly-one-of (user XOR admin)   |
| idx_..._feedback_id      | INDEX           | ON (feedback_id)                  |

# ABAC visibility (ADR-0049 §5.2)

- user: own attachments → signed URL via /api/v1/users/feedbacks/{id} GET
- admin: all attachments → signed URL via admin/feedbacks/{id} GET
- companion: **NEVER** signed URL (RED LINE, ABAC §6 Layer 1+2+3+4)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# admin_users.id BigInteger PG / Integer SQLite (see app.models.admin_user._ID_TYPE).
_ADMIN_ID_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class FeedbackAttachment(Base):
    """One feedback attachment blob reference (ADR-0049 §5.2).

    One UserFeedback (1:N) FeedbackAttachment.

    Created by ``feedback_attachment.record_attachment_after_blob_put``
    after ``feedback_attachment_storage.put_attachment`` successfully
    stages the blob. The DB row is the persistent join (blob ↔ feedback).

    Lifecycle:
    - INSERT only at attachment-bind time (post blob put, pre or with
      feedback row commit)
    - No UPDATE (immutable; if blob changes, new row + new content_hash)
    - DELETE via ``ON DELETE CASCADE`` when parent feedback row deleted
      (rare; mostly admin purge / GDPR right-to-erasure)
    """

    __tablename__ = "feedback_attachments"

    __table_args__ = (
        # Exactly-one-of (uploader is user XOR admin). ADR-0049 §5.2.
        CheckConstraint(
            "(uploaded_by_user_id IS NOT NULL AND uploaded_by_admin_id IS NULL) "
            "OR "
            "(uploaded_by_user_id IS NULL AND uploaded_by_admin_id IS NOT NULL)",
            name="chk_uploaded_by",
        ),
        # idx_feedback_attachments_feedback_id (ADR-0049 §5.2).
        # GET /admin/feedbacks/{id} + GET /users/feedbacks/{id} both lookup
        # via feedback_id; B-tree index keeps the per-feedback fan-out cheap.
        Index(
            "idx_feedback_attachments_feedback_id",
            "feedback_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        comment="附件行 PK (gen_random_uuid)",
    )

    feedback_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user_feedbacks.id", ondelete="CASCADE"),
        nullable=False,
        comment="所属反馈 FK (ON DELETE CASCADE)",
    )

    storage_uri: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="StorageBackend uri (local:// / azure://); never user-controlled path",
    )

    content_type: Mapped[str] = mapped_column(
        String(length=128),
        nullable=False,
        comment="MIME (allowlist enforced upstream in feedback_attachment_storage)",
    )

    byte_size: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="字节数 (上层 10 MiB cap)",
    )

    content_hash: Mapped[str] = mapped_column(
        CHAR(64),
        nullable=False,
        comment="SHA-256 全 64 字符 hex (idempotency / tamper-evident)",
    )

    uploaded_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True,
        comment="用户上传方 (XOR admin, CHECK chk_uploaded_by)",
    )

    uploaded_by_admin_id: Mapped[int | None] = mapped_column(
        _ADMIN_ID_TYPE,
        ForeignKey("admin_users.id"),
        nullable=True,
        comment="admin 代上传方 (XOR user, CHECK chk_uploaded_by)",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        comment="行创建时间 (immutable)",
    )
