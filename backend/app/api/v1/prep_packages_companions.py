"""Companion-facing prep package endpoint (ABAC RED LINE).

ADR-0048 §7.0.2 companion route. **PRD-003 §2.2 + AC-6 PM P0 red line**:
陪诊师端任何路径不可见用户病史原文.

Defense layers stacking up at this endpoint:

1. ``Depends(get_current_companion)`` — must be a JWT user whose
   ``role == UserRole.companion`` (or has companion in multi-role).
   Pure ``get_current_user`` is **deliberately not** reused so a
   patient token cannot reach this surface.
2. service layer ``get_prep_for_companion(order_id, companion_id)`` —
   SELECTs only companion-visible columns AND verifies the companion
   is the assigned servicer for this order.
3. ``response_model=CompanionPrepPackageView`` — the Pydantic model
   *literally does not define* ``pre_visit_notes`` / ``possible_questions``
   / ``trace_id`` / raw ``carry_items``. Even if a buggy service layer
   tried to include them they'd be dropped by ``extra="ignore"``.

The integration sentinel ``test_companion_view_response_field_set_locked``
asserts the response field set is closed (``actual == EXPECTED``) so a
future schema drift that surfaces a forbidden field would fail CI before
merging.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentCompanion, DBSession
from app.schemas.prep_package import CompanionPrepPackageView
from app.services.prep_package_service import PrepPackageService

router = APIRouter(prefix="/companions/orders", tags=["companions-prep-package"])


@router.get(
    "/{order_id}/prep-package",
    response_model=CompanionPrepPackageView,
    summary="陪诊师获取本订单的 AI 准备包 (脱敏视图, 不含病史原文)",
    description=(
        "**红线**: 不含 pre_visit_notes / possible_questions / trace_*; "
        "carry_items 已压缩为 carry_items_summary 短摘要。"
        "仅陪诊师为本订单的指派服务者时返回; 否则返回 404。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_companion_prep_package(
    order_id: UUID,
    current_companion: CurrentCompanion,
    session: DBSession,
) -> CompanionPrepPackageView:
    return await PrepPackageService(session).get_prep_for_companion(
        order_id, current_companion.id
    )
