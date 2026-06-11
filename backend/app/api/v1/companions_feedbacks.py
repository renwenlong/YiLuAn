"""Companion-facing feedback endpoints (ABAC RED LINE).

ADR-0049 §7 companion routes. **PRD-004 §安全边界 + ADR-0049 §6 red line**:
陪诊师端任何路径不可见用户原文 (raw_content) 或附件原图.

# Endpoints (2)

| Method | Path | Purpose |
|---|---|---|
| POST | /companions/feedbacks/{id}/appeal | Companion appeal write |
| GET | /companions/feedbacks/{id}/summary | RED LINE sanitized summary |

# Defense layers (ABAC 4-layer, ADR-0049 §6)

1. ``Depends(get_current_companion)`` — JWT user whose role is companion
   (pure ``get_current_user`` is **deliberately not** reused so a patient
   token cannot reach this surface).
2. Service layer ``get_summary_for_companion`` — SELECTs only 5 columns
   AND verifies ``UserFeedback.companion_id == current_companion.id``.
3. ``response_model=CompanionFeedbackSummaryView`` — the Pydantic model
   *literally does not define* ``raw_content`` / ``metadata`` /
   ``user_phone`` / ``patient_name`` / ``attachments`` / signed URLs.
   Even if a buggy service layer tried to include them they'd be dropped
   by ``extra="ignore"``.
4. Integration sentinel
   ``test_companion_summary_response_field_set_locked`` asserts the
   response field set is closed.

# 404 vs 403 policy

We return 404 (not 403) when the companion_id does not match, to avoid
leaking which feedback ids exist for which companions (enumeration
defense, ADR-0048 §7.0).
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentCompanion, DBSession
from app.schemas.feedback import (
    CompanionAppealRequest,
    CompanionFeedbackSummaryView,
)
from app.services.feedback_service import FeedbackService

router = APIRouter(prefix="/companions/feedbacks", tags=["companions-feedbacks"])


@router.post(
    "/{feedback_id}/appeal",
    response_model=CompanionFeedbackSummaryView,
    response_model_by_alias=False,
    status_code=status.HTTP_200_OK,
    summary="陪诊师对反馈申诉 (写 companion_appeal 字段)",
    description=(
        "陪诊师对反馈写申诉理由. 这个 endpoint 不创建新资源, 仅更新已有 UserFeedback 行 "
        "的 companion_appeal 字段, 所以 200 不是 201 (REST 语义 alignment). "
        "ABAC: 仅 feedback.companion_id == current_companion.id 才能写 "
        "(否则 HTTP 404, 不泄露存在). "
        "返回脱敏摘要视图 (RED LINE 5 字段, 不含 raw_content)."
    ),
    responses={**err(401, 403, 404, 422, 500)},
)
async def companion_appeal_feedback(
    feedback_id: UUID,
    body: CompanionAppealRequest,
    current_companion: CurrentCompanion,
    session: DBSession,
) -> CompanionFeedbackSummaryView:
    service = FeedbackService(session)
    row = await service.record_appeal_for_companion(
        feedback_id=feedback_id,
        companion_user_id=current_companion.id,
        companion_appeal=body.companion_appeal,
    )
    await session.commit()

    # Project to RED LINE summary view (forbidden columns absent).
    # We do NOT pass `row` directly — read fresh via summary projection
    # to ensure the response *literally* has no extra fields (paranoid).
    summary = await service.get_summary_for_companion(
        feedback_id=row.id, companion_user_id=current_companion.id
    )
    return CompanionFeedbackSummaryView.model_validate(summary)


@router.get(
    "/{feedback_id}/summary",
    response_model=CompanionFeedbackSummaryView,
    response_model_by_alias=False,
    summary="陪诊师反馈摘要视图 (RED LINE, 不含病史/附件原图)",
    description=(
        "**红线**: 不含 raw_content / metadata / user_phone / patient_name / "
        "attachments / signed_url / handled_by_admin_id. "
        "仅返 (id, severity, status, sanitized_summary, companion_appeal) 5 字段. "
        "sanitized_summary NULL 表示 admin 未脱敏 — 端展示「等待客服处理」. "
        "仅 feedback.companion_id == current_companion.id 才返; 否则 HTTP 404."
    ),
    responses={**err(401, 403, 404, 500)},
)
async def companion_get_feedback_summary(
    feedback_id: UUID,
    current_companion: CurrentCompanion,
    session: DBSession,
) -> CompanionFeedbackSummaryView:
    service = FeedbackService(session)
    summary = await service.get_summary_for_companion(
        feedback_id=feedback_id,
        companion_user_id=current_companion.id,
    )
    return CompanionFeedbackSummaryView.model_validate(summary)
