"""Admin-facing feedback endpoints (ABAC 4-layer, admin surface).

ADR-0049 §7 admin routes. Customer service / phone / offline channel
admin can record feedback on user's behalf; admin can list/detail/patch
status across all feedbacks.

# Endpoints (4)

| Method | Path | Purpose |
|---|---|---|
| POST | /admin/feedbacks | Admin records feedback on user's behalf |
| GET | /admin/feedbacks | Paginated list with filters |
| GET | /admin/feedbacks/{id} | Full detail (all roles' fields) |
| PATCH | /admin/feedbacks/{id}/status | Status transition |

# Auth model

1. ``Depends(get_current_admin)`` — JWT-only AdminUser (legacy
   X-Admin-Token sentinel rejected; we need a real AdminUser row for
   audit trails).
2. AdminAuditLog row written for state-changing operations (POST create,
   PATCH status, GET detail). Pattern follows admin/prep_packages.py —
   write audit *before* the data fetch so a successful op always has
   audit trace ahead of the costly I/O.

# Audit limitation (intentional, same as admin/prep_packages.py)

Audit row shares the request-scoped transaction with the data op, so
404/500 from the service layer rolls back both. Probe attempts against
non-existent ids are **not** captured. Reconnaissance auditing needs a
second commit boundary; tracked as follow-up (separate ADR), out of
scope for this PR.
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
    Query,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError

from app.api.v1.feedback_ratelimit import feedback_admin_create_ratelimit
from app.api.v1.openapi_meta import err
from app.api.v1.users_feedbacks import _read_uploadfiles
from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.models.user_feedback import (
    FeedbackFunctionModule,
    FeedbackSeverity,
    FeedbackSource,
    FeedbackStatus,
)
from app.schemas.feedback import (
    AdminFeedbackListItem,
    AdminFeedbackListResponse,
    AdminFeedbackPatchStatusRequest,
    UserFeedbackDetailView,
)
from app.services.feedback_service import (
    FeedbackAttachmentContentTypeError,
    FeedbackAttachmentPutError,
    FeedbackAttachmentSizeError,
    FeedbackService,
    InvalidFeedbackStateTransitionError,
)

router = APIRouter(prefix="/feedbacks", tags=["admin-feedbacks"])


# ---------------------------------------------------------------------------
# Admin create body (legacy reference — multipart endpoint above uses Form)
#
# Kept as a Pydantic schema reference so OpenAPI tooling / test fixtures
# have an importable type for the field set. The multipart endpoint
# itself does NOT bind this model (FastAPI does not support both Form
# and Body in one endpoint).
# ---------------------------------------------------------------------------


class AdminCreateFeedbackBody(BaseModel):
    """Admin records feedback on user's behalf (reference schema; multipart
    endpoint above is the real wire format)."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID = Field(description="反馈归属的 user_id (admin 代录目标)")
    feedback_function_module: FeedbackFunctionModule
    category: Annotated[str, Field(min_length=1, max_length=64)]
    severity: FeedbackSeverity
    source: FeedbackSource = Field(
        description="必须是 customer_service / phone / offline; 拒 user"
    )
    raw_content: Annotated[str, Field(min_length=1, max_length=10_000)]
    order_id: UUID | None = None
    companion_id: UUID | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=UserFeedbackDetailView,
    response_model_by_alias=False,
    status_code=status.HTTP_201_CREATED,
    summary="admin 代录反馈 (multipart, customer_service / phone / offline)",
    description=(
        "**multipart/form-data**. 客服/电话/线下代用户录反馈 (可选附件). "
        "source 必须是 {customer_service, phone, offline}, 拒绝 'user' "
        "(admin 不能伪装用户提交). "
        "写入 AdminAuditLog (target_type=user_feedback, action=create). "
        "限频: 60/h per admin (ADR-0049 §3.2.1)."
    ),
    responses={**err(401, 403, 409, 422, 429, 500, 503)},
    dependencies=[Depends(feedback_admin_create_ratelimit)],
)
async def admin_create_feedback(
    current_admin: CurrentAdmin,
    session: DBSession,
    user_id: Annotated[UUID, Form(description="反馈归属的 user_id (admin 代录目标)")],
    feedback_function_module: Annotated[FeedbackFunctionModule, Form()],
    category: Annotated[str, Form(min_length=1, max_length=64)],
    severity: Annotated[FeedbackSeverity, Form()],
    source: Annotated[
        FeedbackSource,
        Form(description="必须是 customer_service / phone / offline; 拒 user"),
    ],
    raw_content: Annotated[str, Form(min_length=1, max_length=10_000)],
    order_id: Annotated[UUID | None, Form()] = None,
    companion_id: Annotated[UUID | None, Form()] = None,
    attachments: Annotated[list[UploadFile] | None, File()] = None,
) -> UserFeedbackDetailView:
    if source is FeedbackSource.user:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="admin-recorded feedback source must not be 'user'",
        )

    attachment_inputs = await _read_uploadfiles(attachments)

    service = FeedbackService(session)
    try:
        row = await service.create_admin_recorded_feedback(
            recording_admin_id=current_admin.id,
            user_id=user_id,
            feedback_function_module=feedback_function_module,
            category=category,
            severity=severity,
            source=source,
            raw_content=raw_content,
            order_id=order_id,
            companion_id=companion_id,
            attachments=attachment_inputs,
        )
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "duplicate_first_feedback: same (user, order, category) "
                "first feedback already exists"
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

    # Audit row (after success — admin_create_feedback is the audit-worthy op).
    audit = AdminAuditLog(
        target_type="user_feedback",
        target_id=row.id,
        action="create",
        operator=current_admin.username,
    )
    session.add(audit)
    await session.commit()
    return UserFeedbackDetailView.model_validate(row)


@router.get(
    "",
    response_model=AdminFeedbackListResponse,
    response_model_by_alias=False,
    summary="admin 反馈列表 + 过滤分页",
    description=(
        "支持过滤: status / severity / module / companion_id. "
        "默认每页 50, 最多 100. "
        "排序: created_at desc."
    ),
    responses={**err(401, 403, 422, 500)},
)
async def admin_list_feedbacks(
    current_admin: CurrentAdmin,
    session: DBSession,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, alias="page_size")] = 50,
    status_filter: Annotated[
        FeedbackStatus | None, Query(alias="status")
    ] = None,
    severity: Annotated[FeedbackSeverity | None, Query()] = None,
    module: Annotated[FeedbackFunctionModule | None, Query()] = None,
    companion_id: Annotated[UUID | None, Query()] = None,
) -> AdminFeedbackListResponse:
    service = FeedbackService(session)
    rows, total = await service.list_feedbacks_for_admin(
        page=page,
        page_size=page_size,
        status=status_filter,
        severity=severity,
        module=module,
        companion_id=companion_id,
    )
    return AdminFeedbackListResponse(
        items=[AdminFeedbackListItem.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{feedback_id}",
    response_model=UserFeedbackDetailView,
    response_model_by_alias=False,
    summary="admin 反馈详情 (全字段)",
    description=(
        "全字段视图. 写入 AdminAuditLog (target_type=user_feedback, action=view); "
        "audit 在外层 transaction commit, fetch 走 SAVEPOINT — 404 仅回滚 fetch, "
        "audit 行仍保留 (probe 审计, ADR-0049 §6.2 魈 review #5 双 commit boundary)."
    ),
    responses={**err(401, 403, 404, 500)},
)
async def admin_get_feedback(
    feedback_id: UUID,
    current_admin: CurrentAdmin,
    session: DBSession,
) -> UserFeedbackDetailView:
    # 阉塞 #5 修复 (魈 review): 双 commit boundary so probe-against-nonexistent-id
    # still leaves an audit row. 上一版 audit + fetch 同事务, 404 回滚 audit 也 回
    # 滚, 与 docstring "write before fetch" 矛盾.
    #
    # Flow:
    # 1. INSERT audit row → commit (outer transaction 结束).
    # 2. SAVEPOINT "audit_safe_fetch" → fetch.
    # 3. 若 fetch raise NotFoundException → rollback to savepoint;
    #    audit 行已 commit, 未被 回滚.
    audit = AdminAuditLog(
        target_type="user_feedback",
        target_id=feedback_id,
        action="view",
        operator=current_admin.username,
    )
    session.add(audit)
    await session.commit()  # audit boundary 1 — 不随 fetch 回滚

    savepoint = await session.begin_nested()
    try:
        service = FeedbackService(session)
        row = await service.get_feedback_for_admin(feedback_id)
        await savepoint.commit()
        return UserFeedbackDetailView.model_validate(row)
    except Exception:
        # 404 / 500 仅 回滚 savepoint; audit 行 保留于 DB.
        await savepoint.rollback()
        raise


@router.patch(
    "/{feedback_id}/status",
    response_model=UserFeedbackDetailView,
    response_model_by_alias=False,
    summary="admin 状态流转 (state-machine 验)",
    description=(
        "UserFeedbackStateMachine 5 状态合法迁移. 非法迁移 → HTTP 409. "
        "首次 pending → in_review 自动设 handled_by_admin_id + handled_at. "
        "迁移到 closed 自动设 closed_at (供后续 user_append 30d 窗口判). "
        "写入 AdminAuditLog (target_type=user_feedback, action=patch_status)."
    ),
    responses={**err(401, 403, 404, 409, 422, 500)},
)
async def admin_patch_feedback_status(
    feedback_id: UUID,
    body: AdminFeedbackPatchStatusRequest,
    current_admin: CurrentAdmin,
    session: DBSession,
) -> UserFeedbackDetailView:
    service = FeedbackService(session)
    try:
        row = await service.patch_status_for_admin(
            feedback_id=feedback_id,
            target_status=body.target_status,
            operating_admin_id=current_admin.id,
            admin_sanitized_summary=body.admin_sanitized_summary,
            admin_resolution_summary=body.admin_resolution_summary,
        )
    except InvalidFeedbackStateTransitionError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc

    # Audit row (after success).
    audit = AdminAuditLog(
        target_type="user_feedback",
        target_id=row.id,
        action=f"patch_status:{body.target_status.value}",
        operator=current_admin.username,
    )
    session.add(audit)
    await session.commit()
    return UserFeedbackDetailView.model_validate(row)
