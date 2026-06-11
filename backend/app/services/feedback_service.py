"""Role-scoped feedback projections + state machine wire (ABAC Layer 3).

ADR-0049 §6.3. Each public method SELECTs only the columns its API view
may expose. This is intentionally stronger than "query ORM row then let
Pydantic filter extras" — forbidden fields should not leave the database
layer for that role at all.

# Method matrix

| Method | Role | Returns |
|---|---|---|
| ``create_user_feedback`` | user | full ``UserFeedback`` |
| ``append_user_feedback`` | user | full ``UserFeedback`` (parent.user_id == user_id) |
| ``get_feedback_for_user`` | user | full row, ownership filter |
| ``list_feedbacks_for_admin`` | admin | list rows + pagination |
| ``get_feedback_for_admin`` | admin | full row, **no** ownership filter |
| ``patch_status_for_admin`` | admin | full row after legal transition |
| ``record_appeal_for_companion`` | companion | full row after appeal write |
| ``get_summary_for_companion`` | companion | RED LINE projection (4 columns only) |

# Append window (ADR-0049 §4.1 closed → in_review)

``append_user_feedback`` validates parent state via
``UserFeedbackStateMachine.assert_user_append_allowed``; 30d window on
closed state raises :class:`FeedbackAppendWindowExpiredError`, the
endpoint layer maps to HTTP 410 Gone.

# Multipart attachments (architect ratify X, 2026-06-11)

ADR-0049 §7.1 specifies multipart endpoints with ``UploadFile`` files.
No separate "staging" endpoint: ``put_attachment`` needs ``feedback_id``
at blob-path construction time, so the flow is **atomic** within
``create_user_feedback`` / ``append_user_feedback`` /
``create_admin_recorded_feedback``:

1. INSERT ``UserFeedback`` row
2. ``await session.flush()`` to materialize ``row.id`` (DB PK)
3. For each attachment bytes blob: synchronous
   ``feedback_attachment_storage.put_attachment(feedback_id=row.id, ...)``
4. ``await feedback_attachment.record_attachment_after_blob_put(...)`` to
   INSERT one ``FeedbackAttachment`` row per blob (idempotent on
   (feedback_id, content_hash))
5. Counter ``feedback_submitted_total{severity, module, source}.inc()``

Caller (endpoint) controls ``session.commit()`` / ``rollback()``.
If any attachment fails, the whole feedback insert is rolled back
(blob may be orphaned; since blob_path is hash-based, future retry
with same bytes is idempotent on the blob layer).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.models.user_feedback import (
    FeedbackFunctionModule,
    FeedbackSeverity,
    FeedbackSource,
    FeedbackStatus,
    UserFeedback,
)
from app.services.feedback_attachment import (
    record_attachment_after_blob_put,
)
from app.services.feedback_attachment_storage import (
    FeedbackAttachmentContentTypeError,
    FeedbackAttachmentPutError,
    FeedbackAttachmentSizeError,
    put_attachment,
)
from app.services.user_feedback_state_machine import (
    FeedbackAppendWindowExpiredError,
    InvalidFeedbackStateTransitionError,
    assert_transition,
    assert_user_append_allowed,
)
from app.utils.metrics import feedback_submitted_total


class FeedbackAttachmentInput:
    """In-memory attachment payload for ``create_*`` / ``append_*``.

    Plain class (NOT a Pydantic model) — read directly from
    ``UploadFile.read()`` at the endpoint layer; service receives bytes
    + content_type. This keeps the multipart streaming concern in the
    endpoint and the service deterministic / synchronous-friendly.
    """

    __slots__ = ("content", "content_type", "filename")

    def __init__(
        self, *, content: bytes, content_type: str, filename: str | None = None
    ) -> None:
        self.content = content
        self.content_type = content_type
        self.filename = filename

logger = logging.getLogger("app.services.feedback_service")


class FeedbackService:
    """ABAC + state-machine wire for user_feedbacks."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # User side
    # ------------------------------------------------------------------

    async def create_user_feedback(
        self,
        *,
        user_id: UUID,
        feedback_function_module: FeedbackFunctionModule,
        category: str,
        severity: FeedbackSeverity,
        raw_content: str,
        order_id: UUID | None = None,
        companion_id: UUID | None = None,
        attachments: list[FeedbackAttachmentInput] | None = None,
    ) -> UserFeedback:
        """Insert first-time feedback row (status=pending, source=user).

        ABAC: user submits own feedback only; ``user_id`` is set from
        current_user (endpoint layer), not from request body.

        Uniqueness: DB partial unique index
        ``uq_user_feedback_once_per_order_category`` prevents
        same-(user_id, order_id, category) first feedback duplication.
        Caller (endpoint) catches IntegrityError → HTTP 409.

        Attachments: see module docstring "Multipart attachments" —
        atomic flow stages blobs after row.flush() and binds them
        before incrementing ``feedback_submitted_total``.
        Caller controls commit/rollback.
        """
        row = UserFeedback(
            user_id=user_id,
            feedback_function_module=feedback_function_module,
            category=category,
            severity=severity,
            source=FeedbackSource.user,
            raw_content=raw_content,
            order_id=order_id,
            companion_id=companion_id,
            status=FeedbackStatus.pending,
        )
        self._session.add(row)
        await self._session.flush()

        if attachments:
            await self._bind_attachments(
                row=row,
                attachments=attachments,
                uploaded_by_user_id=user_id,
                uploaded_by_admin_id=None,
            )

        # ADR-0049 §4.2: feedback_submitted_total drives Alertmanager
        # UrgentFeedbackSubmitted (severity=urgent triggers alert).
        feedback_submitted_total.labels(
            severity=severity.value,
            module=feedback_function_module.value,
            source=FeedbackSource.user.value,
        ).inc()
        return row

    async def append_user_feedback(
        self,
        *,
        parent_feedback_id: UUID,
        user_id: UUID,
        raw_content: str,
        attachments: list[FeedbackAttachmentInput] | None = None,
    ) -> UserFeedback:
        """Append supplementary feedback (ADR-0049 §7.1).

        ABAC: parent.user_id must == user_id (endpoint also enforces
        before reaching here; service-layer check is defense in depth).

        State machine: parent state must allow user_append
        (``assert_user_append_allowed``). If parent is ``closed``, the
        30d window is checked; expired → ``FeedbackAppendWindowExpiredError``
        which endpoint layer maps to HTTP 410.

        After successful append, parent state transitions to ``in_review``
        (the act of user_append always reactivates the parent).

        Attachments are bound to the child row (NOT the parent).
        """
        parent = await self._get_for_user_or_404(parent_feedback_id, user_id)

        # State machine compound guard: append permission + 30d window check.
        # Raises:
        #   - InvalidFeedbackStateTransitionError if parent state disallows
        #     append (pending / in_review)
        #   - FeedbackAppendWindowExpiredError if closed > 30d
        # Endpoint layer maps to HTTP 409 / 410 respectively.
        assert_user_append_allowed(
            from_status=parent.status,
            closed_at=parent.closed_at,
        )

        # Insert child row inheriting parent classification (§7.1 body =
        # raw_content + attachments only; everything else inherited).
        child = UserFeedback(
            feedback_parent_id=parent.id,
            user_id=user_id,
            order_id=parent.order_id,
            companion_id=parent.companion_id,
            feedback_function_module=parent.feedback_function_module,
            category=parent.category,
            severity=parent.severity,
            source=FeedbackSource.user,
            raw_content=raw_content,
            status=FeedbackStatus.pending,
        )
        self._session.add(child)

        # Parent transitions to in_review (reactivation).
        parent.status = FeedbackStatus.in_review
        parent.updated_at = datetime.now(timezone.utc)

        await self._session.flush()

        if attachments:
            await self._bind_attachments(
                row=child,
                attachments=attachments,
                uploaded_by_user_id=user_id,
                uploaded_by_admin_id=None,
            )

        # Append counts as a fresh submission for alert/metrics purposes.
        feedback_submitted_total.labels(
            severity=child.severity.value,
            module=child.feedback_function_module.value,
            source=FeedbackSource.user.value,
        ).inc()
        return child

    async def get_feedback_for_user(
        self, feedback_id: UUID, user_id: UUID
    ) -> UserFeedback:
        """Return user's own feedback row (full content)."""
        return await self._get_for_user_or_404(feedback_id, user_id)

    # ------------------------------------------------------------------
    # Admin side
    # ------------------------------------------------------------------

    async def create_admin_recorded_feedback(
        self,
        *,
        recording_admin_id: int,
        user_id: UUID,
        feedback_function_module: FeedbackFunctionModule,
        category: str,
        severity: FeedbackSeverity,
        source: FeedbackSource,
        raw_content: str,
        order_id: UUID | None = None,
        companion_id: UUID | None = None,
        attachments: list[FeedbackAttachmentInput] | None = None,
    ) -> UserFeedback:
        """admin 代录反馈 (POST /api/v1/admin/feedbacks).

        ABAC: ``source`` must be one of
        {customer_service, phone, offline} (NOT user — admin can't fake
        user direct submission). Endpoint layer validates before reaching
        service.

        ``handled_by_admin_id`` is **not** set here — that's the
        ``admin_start_review`` operator, distinct from the recording
        admin. Audit linkage via AdminAuditLog row (endpoint layer).

        Attachments are attributed to ``uploaded_by_admin_id=recording_admin_id``
        (XOR with user; CHECK chk_uploaded_by enforced at DB level).
        """
        if source is FeedbackSource.user:
            raise ValueError(
                "admin-recorded feedback source must not be 'user'"
            )
        row = UserFeedback(
            user_id=user_id,
            feedback_function_module=feedback_function_module,
            category=category,
            severity=severity,
            source=source,
            raw_content=raw_content,
            order_id=order_id,
            companion_id=companion_id,
            status=FeedbackStatus.pending,
        )
        self._session.add(row)
        await self._session.flush()

        if attachments:
            await self._bind_attachments(
                row=row,
                attachments=attachments,
                uploaded_by_user_id=None,
                uploaded_by_admin_id=recording_admin_id,
            )

        feedback_submitted_total.labels(
            severity=severity.value,
            module=feedback_function_module.value,
            source=source.value,
        ).inc()
        return row

    async def list_feedbacks_for_admin(
        self,
        *,
        page: int = 1,
        page_size: int = 50,
        status: FeedbackStatus | None = None,
        severity: FeedbackSeverity | None = None,
        module: FeedbackFunctionModule | None = None,
        companion_id: UUID | None = None,
    ) -> tuple[list[UserFeedback], int]:
        """Admin paginated list with optional filters."""
        page = max(1, page)
        page_size = max(1, min(100, page_size))

        stmt = select(UserFeedback)
        count_stmt = select(func.count(UserFeedback.id))

        if status is not None:
            stmt = stmt.where(UserFeedback.status == status)
            count_stmt = count_stmt.where(UserFeedback.status == status)
        if severity is not None:
            stmt = stmt.where(UserFeedback.severity == severity)
            count_stmt = count_stmt.where(UserFeedback.severity == severity)
        if module is not None:
            stmt = stmt.where(UserFeedback.feedback_function_module == module)
            count_stmt = count_stmt.where(
                UserFeedback.feedback_function_module == module
            )
        if companion_id is not None:
            stmt = stmt.where(UserFeedback.companion_id == companion_id)
            count_stmt = count_stmt.where(
                UserFeedback.companion_id == companion_id
            )

        stmt = (
            stmt.order_by(UserFeedback.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        rows = (await self._session.execute(stmt)).scalars().all()
        total = (await self._session.execute(count_stmt)).scalar_one()
        return list(rows), int(total)

    async def get_feedback_for_admin(self, feedback_id: UUID) -> UserFeedback:
        """Return any feedback row (admin sees everything)."""
        row = await self._session.get(UserFeedback, feedback_id)
        if row is None:
            raise NotFoundException(f"feedback {feedback_id} not found")
        return row

    async def patch_status_for_admin(
        self,
        *,
        feedback_id: UUID,
        target_status: FeedbackStatus,
        operating_admin_id: int,
        admin_sanitized_summary: str | None = None,
        admin_resolution_summary: str | None = None,
    ) -> UserFeedback:
        """Admin status transition (state-machine validated).

        - ``handled_by_admin_id`` is set on first transition to
          ``in_review`` (pending → in_review).
        - ``handled_at`` is set on same first transition.
        - ``closed_at`` is set when transitioning to ``closed``.

        Illegal transition raises
        :class:`InvalidFeedbackStateTransitionError`; endpoint layer
        maps to HTTP 409.
        """
        row = await self.get_feedback_for_admin(feedback_id)

        # State machine validates legality (raises on illegal).
        assert_transition(from_status=row.status, to_status=target_status)

        # Side effects of specific transitions.
        if (
            row.status is FeedbackStatus.pending
            and target_status is FeedbackStatus.in_review
        ):
            row.handled_by_admin_id = operating_admin_id
            row.handled_at = datetime.now(timezone.utc)

        if target_status is FeedbackStatus.closed:
            row.closed_at = datetime.now(timezone.utc)

        if admin_sanitized_summary is not None:
            row.admin_sanitized_summary = admin_sanitized_summary
        if admin_resolution_summary is not None:
            row.admin_resolution_summary = admin_resolution_summary

        row.status = target_status
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row

    # ------------------------------------------------------------------
    # Companion side — RED LINE
    # ------------------------------------------------------------------

    async def record_appeal_for_companion(
        self,
        *,
        feedback_id: UUID,
        companion_user_id: UUID,
        companion_appeal: str,
    ) -> UserFeedback:
        """陪诊师 appeal write (ABAC: only the targeted companion).

        ``companion_user_id`` is the User.id of the JWT-authenticated
        companion. The FK on ``user_feedbacks.companion_id`` points to
        ``companion_profiles.id``, so we join through CompanionProfile
        to enforce ownership.

        Returns full row (caller projects to ``CompanionFeedbackSummaryView``
        before returning to companion endpoint — RED LINE).
        """
        from app.models.companion_profile import CompanionProfile

        stmt = (
            select(UserFeedback)
            .join(
                CompanionProfile,
                CompanionProfile.id == UserFeedback.companion_id,
            )
            .where(
                UserFeedback.id == feedback_id,
                CompanionProfile.user_id == companion_user_id,
            )
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            # Not 403 — 404 (避免柚扣 companion_id 与 feedback_id 关系).
            raise NotFoundException(f"feedback {feedback_id} not found")

        row.companion_appeal = companion_appeal
        row.updated_at = datetime.now(timezone.utc)
        await self._session.flush()
        return row

    async def get_summary_for_companion(
        self, feedback_id: UUID, companion_user_id: UUID
    ) -> dict:
        """RED LINE: 陪诊师摘要视图 — SELECT 列裁剪.

        SELECTs only 5 columns; forbidden columns
        (``raw_content`` / ``metadata`` / FK ``user_id`` / attachments /
        ``handled_by_admin_id``) **never leave the DB** for this role.

        Ownership enforced via JOIN through CompanionProfile because
        ``user_feedbacks.companion_id`` points to ``companion_profiles.id``,
        not ``users.id``.

        Even if a buggy downstream code tried to access
        ``UserFeedback.raw_content`` on the returned dict, it would
        KeyError — that's intentional defense.
        """
        from app.models.companion_profile import CompanionProfile

        stmt = (
            select(
                UserFeedback.id.label("feedback_id"),
                UserFeedback.severity,
                UserFeedback.status,
                UserFeedback.admin_sanitized_summary.label("sanitized_summary"),
                UserFeedback.companion_appeal,
            )
            .join(
                CompanionProfile,
                CompanionProfile.id == UserFeedback.companion_id,
            )
            .where(
                UserFeedback.id == feedback_id,
                CompanionProfile.user_id == companion_user_id,
            )
        )
        row = (await self._session.execute(stmt)).mappings().one_or_none()
        if row is None:
            raise NotFoundException(f"feedback {feedback_id} not found")
        return dict(row)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _bind_attachments(
        self,
        *,
        row: UserFeedback,
        attachments: list[FeedbackAttachmentInput],
        uploaded_by_user_id: UUID | None,
        uploaded_by_admin_id: int | None,
    ) -> None:
        """Stage blobs + persist FeedbackAttachment rows (atomic w/ feedback).

        Raises:
            FeedbackAttachmentContentTypeError: bad content_type
            FeedbackAttachmentSizeError: > 10 MiB
            FeedbackAttachmentPutError: blob put failed
            FeedbackAttachmentRecordError: DB INSERT failed (XOR / FK)

        Caller (endpoint) maps the first three to HTTP 422 (client) or
        503 (storage). Anything raised here aborts the entire feedback
        insert via session rollback (idempotent: blob bytes are
        hash-named so retry with same payload is dedup-safe).
        """
        for att in attachments:
            ref = put_attachment(
                feedback_id=row.id.hex,
                content=att.content,
                content_type=att.content_type,
            )
            await record_attachment_after_blob_put(
                self._session,
                feedback_id=row.id,
                ref=ref,
                uploaded_by_user_id=uploaded_by_user_id,
                uploaded_by_admin_id=uploaded_by_admin_id,
            )

    async def _get_for_user_or_404(
        self, feedback_id: UUID, user_id: UUID
    ) -> UserFeedback:
        stmt = select(UserFeedback).where(
            UserFeedback.id == feedback_id,
            UserFeedback.user_id == user_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise NotFoundException(f"feedback {feedback_id} not found")
        return row


__all__ = [
    "FeedbackService",
    "FeedbackAttachmentInput",
    "FeedbackAppendWindowExpiredError",
    "InvalidFeedbackStateTransitionError",
    "FeedbackAttachmentContentTypeError",
    "FeedbackAttachmentSizeError",
    "FeedbackAttachmentPutError",
]
