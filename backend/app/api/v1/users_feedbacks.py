"""User-facing feedback endpoints (ABAC 4-layer defense, user surface).

ADR-0049 §7 user routes. Patient/family submits and appends own feedback.

# Endpoints (2)

| Method | Path | Purpose |
|---|---|---|
| POST | /users/feedbacks | First-time feedback submission (multipart) |
| POST | /users/feedbacks/{parent_id}/append | Supplementary feedback (multipart, §7.1) |

# ABAC stack

1. ``Depends(get_current_user)`` — JWT-authenticated user
2. Service layer ``FeedbackService`` — user_id always derived from
   current_user (NEVER from request body)
3. ``response_model=UserFeedbackDetailView`` — Pydantic schema drops
   admin-only fields if service accidentally returned them
4. Append-target ownership: ``parent.user_id == current_user.id``
   enforced in ``FeedbackService.append_user_feedback``

# Why a separate file from admin / companion endpoints

ADR-0049 §6.2: 3 separate routers + role-strict Depends so reviewer can
grep each role's surface area independently. An accidental
``include_router`` mix-up surfaces as obvious diff.

# Multipart attachment flow (architect ratify X, 2026-06-11)

Per ADR-0049 §7.1 the canonical request shape is ``multipart/form-data``:
form fields + ``UploadFile`` parts in a SINGLE POST. No separate
"staging" endpoint — ``feedback_attachment_storage.put_attachment``
requires the ``feedback_id`` at blob-path construction (architect
verified that the staging+bind alternative is physically infeasible
without a multi-step storage redesign).

Attachment failure (bad mime / oversize / blob put error) aborts the
entire request; we do not partially commit a feedback row and leave the
caller wondering which blobs landed.

# Rate limit (阻塞 #2 修复)

``user_submit_feedback_ratelimit`` Depends enforces ADR-0049 §3.2.1
sliding-window quota:
- POST /users/feedbacks: 10/h + 50/d per user
- POST /users/feedbacks/{parent}/append: 30/h + 100/d per user
429 + Retry-After + ``feedback_ratelimit_429_total{endpoint=...}.inc()``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy.exc import IntegrityError

from app.api.v1.feedback_ratelimit import (
    feedback_append_ratelimit,
    feedback_submit_ratelimit,
)
from app.api.v1.openapi_meta import err
from app.dependencies import DBSession, WriteableUser
from app.models.user_feedback import FeedbackFunctionModule, FeedbackSeverity
from app.schemas.feedback import UserFeedbackDetailView
from app.services.feedback_service import (
    FeedbackAppendWindowExpiredError,
    FeedbackAttachmentContentTypeError,
    FeedbackAttachmentInput,
    FeedbackAttachmentPutError,
    FeedbackAttachmentSizeError,
    FeedbackService,
    InvalidFeedbackStateTransitionError,
)

router = APIRouter(prefix="/users/feedbacks", tags=["users-feedbacks"])


async def _read_uploadfiles(
    files: list[UploadFile] | None,
) -> list[FeedbackAttachmentInput]:
    """Drain ``UploadFile`` parts into ``FeedbackAttachmentInput`` list."""
    if not files:
        return []
    inputs: list[FeedbackAttachmentInput] = []
    for upload in files:
        if upload.filename is None and not upload.content_type:
            # Defensive: empty multipart slot.
            continue
        data = await upload.read()
        if not data:
            continue
        inputs.append(
            FeedbackAttachmentInput(
                content=data,
                content_type=(upload.content_type or "application/octet-stream"),
                filename=upload.filename,
            )
        )
    return inputs


@router.post(
    "",
    response_model=UserFeedbackDetailView,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary="用户/家属提交首条反馈 (multipart, ADR-0049 §7)",
    description=(
        "**multipart/form-data**. 文本字段 + 可选 attachments[] 文件流, 一次性 POST. "
        "user_id 取自 JWT, 不接受请求体覆盖. "
        "状态机初始: pending; admin 触达后流转 in_review → resolved/rejected → closed. "
        "唯一约束: 同 user 对同 order 同 category 不可重复首条 (partial unique index "
        "uq_user_feedback_once_per_order_category, parent IS NULL). 重复 → HTTP 409. "
        "限频: 10/h + 50/d per user (ADR-0049 §3.2.1)."
    ),
    responses={**err(401, 409, 422, 429, 500, 503)},
    dependencies=[Depends(feedback_submit_ratelimit)],
)
async def submit_user_feedback(
    current_user: WriteableUser,
    session: DBSession,
    feedback_function_module: Annotated[FeedbackFunctionModule, Form()],
    category: Annotated[str, Form(min_length=1, max_length=64)],
    severity: Annotated[FeedbackSeverity, Form()],
    raw_content: Annotated[str, Form(min_length=1, max_length=10_000)],
    order_id: Annotated[UUID | None, Form()] = None,
    companion_id: Annotated[UUID | None, Form()] = None,
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> UserFeedbackDetailView:
    attachment_inputs = await _read_uploadfiles(attachments)

    service = FeedbackService(session)
    try:
        row = await service.create_user_feedback(
            user_id=current_user.id,
            feedback_function_module=feedback_function_module,
            category=category,
            severity=severity,
            raw_content=raw_content,
            order_id=order_id,
            companion_id=companion_id,
            attachments=attachment_inputs,
        )
    except IntegrityError as exc:
        # Partial unique index hit: same user/order/category first feedback.
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "duplicate_first_feedback: same (user, order, category) "
                "first feedback already exists; use /append for supplements"
            ),
        ) from exc
    except (
        FeedbackAttachmentContentTypeError,
        FeedbackAttachmentSizeError,
    ) as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except FeedbackAttachmentPutError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"attachment storage unavailable: {exc}",
        ) from exc

    await session.commit()
    return UserFeedbackDetailView.model_validate(row)


@router.post(
    "/{parent_id}/append",
    response_model=UserFeedbackDetailView,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary="用户补充已有反馈 (multipart, ADR-0049 §7.1)",
    description=(
        "**multipart/form-data**. 对已有反馈追加内容 (可选附件). "
        "鉴权: parent.user_id == current_user.id. "
        "状态机要求: parent 处于 resolved/rejected/closed 才允许 append "
        "(pending/in_review 拒绝, HTTP 409). "
        "closed → in_review 受 30d 窗口限, 超期返 HTTP 410 Gone. "
        "append 成功后 parent 重新激活到 in_review. "
        "限频: 30/h + 100/d per user (ADR-0049 §3.2.1)."
    ),
    responses={**err(401, 404, 409, 410, 422, 429, 500, 503)},
    dependencies=[Depends(feedback_append_ratelimit)],
)
async def append_user_feedback(
    parent_id: UUID,
    current_user: WriteableUser,
    session: DBSession,
    raw_content: Annotated[str, Form(min_length=1, max_length=10_000)],
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> UserFeedbackDetailView:
    attachment_inputs = await _read_uploadfiles(attachments)

    service = FeedbackService(session)
    try:
        child = await service.append_user_feedback(
            parent_feedback_id=parent_id,
            user_id=current_user.id,
            raw_content=raw_content,
            attachments=attachment_inputs,
        )
    except FeedbackAppendWindowExpiredError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail=str(exc),
        ) from exc
    except InvalidFeedbackStateTransitionError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (
        FeedbackAttachmentContentTypeError,
        FeedbackAttachmentSizeError,
    ) as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except FeedbackAttachmentPutError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"attachment storage unavailable: {exc}",
        ) from exc

    await session.commit()
    return UserFeedbackDetailView.model_validate(child)
