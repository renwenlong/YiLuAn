"""ABAC 4-layer view schemas for user feedback (ADR-0049 §6).

# Role-specific views (Layer 1: Schema)

5 Pydantic views enforce **field-level access control**:

- ``UserFeedbackSubmitRequest`` — user submit body (POST /api/v1/users/feedbacks)
- ``UserFeedbackAppendRequest`` — user append body (POST .../{parent_id}/append)
- ``UserFeedbackDetailView`` — patient/admin-facing full content (含 raw_content)
- ``AdminFeedbackListItem`` — admin list row (轻量, 无 raw_content full)
- ``AdminFeedbackPatchStatusRequest`` — admin PATCH status body
- ``CompanionFeedbackSummaryView`` — **RED LINE**: 陪诊师端摘要视图,
  字段集 frozen, 不含 raw_content / metadata / attachments / user_phone / patient_name
- ``CompanionAppealRequest`` — 陪诊师申诉 body

The companion summary view's safety property is not "set to None" or
"redacted empty" — those fields are **literally absent from the Pydantic
model**. Even if the service layer accidentally returns extra fields,
Pydantic's ``ConfigDict(extra="ignore")`` will silently drop them.

# Defense in depth (ADR-0049 §6 + ADR-0048 §7.0)

- Layer 1: Schema — this file (forbidden fields physically absent)
- Layer 2: Endpoint — 3 separate routers + role-strict Depends
- Layer 3: Service — SELECT column trimming at DB layer
- Layer 4: Test — schema sentinel + integration response_field_set lock

# Positive list (Schemathesis CI lint, ADR-0049 §6.4)

``FEEDBACK_RESPONSE_POSITIVE_LIST`` is the closed set of field names that
may appear in **any** feedback endpoint response. CI lint scans response
JSON keys; any name not in the set fails the build. Adding a field
requires PR + reviewer ack; no runtime extension.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.user_feedback import (
    FeedbackFunctionModule,
    FeedbackSeverity,
    FeedbackSource,
    FeedbackStatus,
)

# ---------------------------------------------------------------------------
# Positive list (ADR-0049 §6.4 刻晴 review #7 amend)
# ---------------------------------------------------------------------------

FEEDBACK_RESPONSE_POSITIVE_LIST: frozenset[str] = frozenset(
    {
        # identity
        "feedback_id",
        "feedback_parent_id",
        # classification
        "feedback_function_module",
        "category",
        "severity",
        "status",
        "source",
        # content (role-gated)
        "raw_content",
        "sanitized_summary",
        "admin_resolution_summary",
        "companion_appeal",
        # association
        "order_id",
        "companion_id",
        "user_id",
        "admin_id",
        # attachments
        "attachments",
        "appeals",
        # timestamps
        "created_at",
        "updated_at",
        "handled_at",
        "closed_at",
        # admin metadata
        "metadata",
        # pagination
        "items",
        "total",
        "page",
        "page_size",
    }
)
"""Closed set of field names allowed in feedback endpoint responses.

Adding a field requires PR + reviewer ack. Used by Schemathesis CI
lint (`tests/contract/test_feedback_positive_list.py`) to fail builds
when an endpoint response contains an unexpected field name.
"""


# Negative list (cross-domain forbidden, ADR-0049 §6.4)
# Used by schema sentinel test (NOT runtime check — defense via positive list).
#
# NOTE on field constraints:
# - ``raw_content`` ``max_length=10_000`` is **application-layer cap** (not
#   in ADR-0049 §3.1 DDL where TEXT is unbounded). Defends against DoS /
#   over-length submissions / unbounded LLM cost on the future S4 summary
#   axis. Change requires PR + reviewer ack.
# - ``companion_appeal`` / ``admin_resolution_summary`` / ``admin_sanitized_summary``
#   ``max_length=4_000`` similarly application-layer (DDL is TEXT).
FEEDBACK_RESPONSE_NEGATIVE_LIST: frozenset[str] = frozenset(
    {
        # cross-domain (ADR-0046 §3.5 + ADR-0048 §7.0)
        "contract_hash",
        "contract_storage_blob_path",
        "insurance_carrier_internal_id",
        "insurance_actual_premium",
        "preparation_prompt_version",
        "preparation_raw_llm_output",
        "share_token_hash",
        # feedback domain forbidden on companion summary
        "raw_content_full",
        "user_phone",
        "user_real_name",
        "patient_name",
        "attachment_blob_path",
        "attachment_storage_key",
        "feedback_internal_notes",
        "admin_review_comments",
        "admin_user_id",
        "companion_real_name",
        "companion_id_card_hash",
        "companion_phone",
    }
)
"""Field names that **must not** appear in companion summary response.

Asserted in unit test `test_companion_summary_field_set_locked`.
"""


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class _BaseFeedbackFields(BaseModel):
    """ORM-mode + drop unknown fields (defense in depth).

    ``populate_by_name=True`` allows Pydantic to accept either the
    field's alias (matching ORM column, e.g. ``id``) OR the field's
    Python name (the public API contract, e.g. ``feedback_id``).
    Endpoints use ``response_model_by_alias=False`` so the wire format
    is the public Python name.
    """

    model_config = ConfigDict(
        from_attributes=True, extra="ignore", populate_by_name=True
    )


# ---------------------------------------------------------------------------
# User-side request bodies
# ---------------------------------------------------------------------------


class UserFeedbackSubmitRequest(BaseModel):
    """User submit feedback body (POST /api/v1/users/feedbacks).

    Per ADR-0049 §3.1, all three FKs (``order_id`` / ``companion_id``) are
    optional (NULL = platform-level / non-companion feedback).

    NOTE on attachments (architect ratify X, 2026-06-11): per ADR-0049
    §7.1 the canonical endpoint form is ``multipart/form-data`` with
    ``UploadFile`` parts; clients submit text fields + attachment files
    in a SINGLE POST. There is no separate "staging" endpoint because
    ``feedback_attachment_storage.put_attachment`` requires the
    feedback_id at blob-path construction time (architect verified, Y
    is physically infeasible). This Pydantic model defines text fields
    only; the endpoint binds them via ``Form(...)`` + ``UploadFile``
    list parameters.
    """

    model_config = ConfigDict(extra="forbid")

    feedback_function_module: FeedbackFunctionModule
    category: Annotated[str, Field(min_length=1, max_length=64)]
    severity: FeedbackSeverity
    raw_content: Annotated[str, Field(min_length=1, max_length=10_000)]
    order_id: UUID | None = None
    companion_id: UUID | None = None


class UserFeedbackAppendRequest(BaseModel):
    """User append (supplementary) feedback body.

    ADR-0049 §7.1: parent.user_id must == current_user.id.
    Classification fields are inherited from parent and **not** re-supplied.

    Attachments via multipart on the endpoint (see ``UserFeedbackSubmitRequest``
    docstring); this model defines text fields only.
    """

    model_config = ConfigDict(extra="forbid")

    raw_content: Annotated[str, Field(min_length=1, max_length=10_000)]


# ---------------------------------------------------------------------------
# Attachment views (used inside detail views)
# ---------------------------------------------------------------------------


class FeedbackAttachmentView(_BaseFeedbackFields):
    """Attachment metadata + signed URL (TTL ≤15min per ADR-0048).

    Returned to user/admin endpoints. **Never** returned to companion
    endpoints (ABAC red line — companion never gets signed URLs).
    """

    attachment_id: UUID = Field(alias="id")
    content_type: str
    byte_size: int
    signed_url: str
    signed_url_expires_at: datetime


# ---------------------------------------------------------------------------
# User / Admin detail view (full content)
# ---------------------------------------------------------------------------


class UserFeedbackDetailView(_BaseFeedbackFields):
    """User self-view + admin detail view (full content)."""

    feedback_id: UUID = Field(alias="id")
    feedback_parent_id: UUID | None
    feedback_function_module: FeedbackFunctionModule
    category: str
    severity: FeedbackSeverity
    status: FeedbackStatus
    source: FeedbackSource
    raw_content: str
    admin_resolution_summary: str | None = None
    order_id: UUID | None
    companion_id: UUID | None
    user_id: UUID
    attachments: list[FeedbackAttachmentView] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    handled_at: datetime | None = None
    closed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Admin list view (lightweight, no full raw_content)
# ---------------------------------------------------------------------------


class AdminFeedbackListItem(_BaseFeedbackFields):
    """Admin list row. ``raw_content`` is truncated to a preview."""

    feedback_id: UUID = Field(alias="id")
    feedback_function_module: FeedbackFunctionModule
    category: str
    severity: FeedbackSeverity
    status: FeedbackStatus
    source: FeedbackSource
    order_id: UUID | None
    companion_id: UUID | None
    user_id: UUID
    created_at: datetime
    handled_at: datetime | None = None


class AdminFeedbackListResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[AdminFeedbackListItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# Admin patch status body
# ---------------------------------------------------------------------------


class AdminFeedbackPatchStatusRequest(BaseModel):
    """Admin PATCH /api/v1/admin/feedbacks/{id}/status body.

    ``target_status`` must be a legal next state per
    :class:`UserFeedbackStateMachine`; endpoint layer asserts using
    ``assert_transition()`` and returns HTTP 409 on illegal moves.
    """

    model_config = ConfigDict(extra="forbid")

    target_status: FeedbackStatus
    admin_resolution_summary: Annotated[str, Field(max_length=4_000)] | None = None
    admin_sanitized_summary: Annotated[str, Field(max_length=4_000)] | None = None


# ---------------------------------------------------------------------------
# Companion side — RED LINE views
# ---------------------------------------------------------------------------


class CompanionAppealRequest(BaseModel):
    """Companion appeal body. ``companion_appeal`` is the only writeable
    field; companion cannot change status / resolution / other fields.
    """

    model_config = ConfigDict(extra="forbid")

    companion_appeal: Annotated[str, Field(min_length=1, max_length=4_000)]


class CompanionFeedbackSummaryView(_BaseFeedbackFields):
    """RED LINE: 陪诊师端摘要视图. Field set is **frozen**.

    Forbidden fields (asserted in test_companion_summary_field_set_locked):
    - raw_content / metadata / user_phone / patient_name
    - attachments / signed_url (no signed URLs to companion)
    - admin_user_id / admin_review_comments

    Only the admin-curated ``sanitized_summary`` is exposed (NULL if not
    yet curated; companion sees "等待客服处理" placeholder).
    """

    feedback_id: UUID
    severity: FeedbackSeverity
    status: FeedbackStatus
    sanitized_summary: str | None = None
    companion_appeal: str | None = None
