"""Feedback attachment service helper (S3-DEV-004-FEEDBACK-API / ADR-0049).

# Scope

Bridges the blob staging layer (``feedback_attachment_storage.put_attachment``
→ ``FeedbackAttachmentRef`` dataclass) and the DB row layer
(``FeedbackAttachment`` ORM). Callers are:

- POST /api/v1/users/feedbacks (user submit; attachments must already be
  staged blob-side with a separate /api/v1/users/feedbacks/attachments
  endpoint — out of scope for this task)
- POST /api/v1/users/feedbacks/{parent}/append
- POST /api/v1/admin/feedbacks (customer service code path)

# Why a separate module

Keeps ``feedback_service.py`` focused on FeedbackService (state machine,
list/get/patch, ABAC SELECT). Attachment-bind is mechanical (idempotent
INSERT) and has its own error surface (orphan blob / duplicate row /
content_hash collision).

# Pattern (mirrors contract_storage + service_contract.py pairing)

``feedback_attachment_storage.put_attachment``:
    blob layer; returns ``FeedbackAttachmentRef`` (blob_path, content_hash,
    content_type, byte_size, stored, already_exists).

``feedback_attachment.record_attachment_after_blob_put`` (this module):
    DB row layer; persists ``FeedbackAttachment`` row binding blob to
    feedback. Idempotent on (feedback_id, content_hash).

# Idempotency

If ``record_attachment_after_blob_put`` is called twice with the same
``feedback_id`` + ``content_hash`` (e.g. client retry), the SECOND call
returns the existing row (no duplicate INSERT). Mirrors blob layer
``already_exists=True`` behavior.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feedback_attachment import FeedbackAttachment
from app.services.feedback_attachment_storage import FeedbackAttachmentRef


class FeedbackAttachmentRecordError(RuntimeError):
    """Raised when persistence step fails after blob put.

    Caller should consider the blob orphaned and surface a 5xx; manual
    cleanup of orphan blobs is OK since blob path is hash-based (re-upload
    of identical bytes → ``already_exists=True``).
    """


async def record_attachment_after_blob_put(
    session: AsyncSession,
    *,
    feedback_id: uuid.UUID,
    ref: FeedbackAttachmentRef,
    uploaded_by_user_id: uuid.UUID | None = None,
    uploaded_by_admin_id: int | None = None,
) -> FeedbackAttachment:
    """Persist a FeedbackAttachment row after blob staging.

    Args:
        session: async DB session in caller's transaction
            (does NOT commit; caller controls boundary).
        feedback_id: parent feedback row id.
        ref: blob staging result from
            :func:`feedback_attachment_storage.put_attachment`.
        uploaded_by_user_id: user attribution (XOR admin, CHECK enforced
            at DB level).
        uploaded_by_admin_id: admin attribution (XOR user).

    Returns:
        Persisted (or pre-existing) :class:`FeedbackAttachment`.

    Raises:
        ValueError: when both / neither uploader fields are set.
        FeedbackAttachmentRecordError: when DB insert fails for non-uniqueness
            reasons (caller should treat blob as orphaned).
    """
    if (uploaded_by_user_id is None) == (uploaded_by_admin_id is None):
        # XOR check (Python-level mirror of CHECK chk_uploaded_by).
        # Both None → reject; both set → reject.
        raise ValueError(
            "exactly one of uploaded_by_user_id / uploaded_by_admin_id must be set"
        )

    # Idempotency: if a row with the same (feedback_id, content_hash) exists,
    # return it. Two clients submitting the same blob in parallel → second
    # call returns first call's row (no duplicate, no INSERT race window).
    existing = await session.execute(
        select(FeedbackAttachment).where(
            FeedbackAttachment.feedback_id == feedback_id,
            FeedbackAttachment.content_hash == ref.content_hash,
        )
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None:
        return existing_row

    row = FeedbackAttachment(
        feedback_id=feedback_id,
        storage_uri=ref.stored.uri,
        content_type=ref.content_type,
        byte_size=ref.byte_size,
        content_hash=ref.content_hash,
        uploaded_by_user_id=uploaded_by_user_id,
        uploaded_by_admin_id=uploaded_by_admin_id,
    )
    session.add(row)
    try:
        await session.flush()  # surface CHECK / FK violations early
    except Exception as exc:  # pragma: no cover - defensive
        raise FeedbackAttachmentRecordError(
            f"failed to persist FeedbackAttachment for feedback={feedback_id}: {exc}"
        ) from exc
    return row


async def list_attachments_for_feedback(
    session: AsyncSession,
    *,
    feedback_id: uuid.UUID,
) -> Sequence[FeedbackAttachment]:
    """List all attachments for a feedback row (caller does ABAC).

    Returns rows ordered by ``created_at ASC`` (display order = upload order).
    """
    result = await session.execute(
        select(FeedbackAttachment)
        .where(FeedbackAttachment.feedback_id == feedback_id)
        .order_by(FeedbackAttachment.created_at.asc())
    )
    return result.scalars().all()
