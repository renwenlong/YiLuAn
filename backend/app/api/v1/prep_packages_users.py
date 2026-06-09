"""User-facing prep package endpoint (ABAC 4-layer defense, Layer 2).

ADR-0048 §7.0.2 user route. The patient pulls their own AI prep
package for an order they own. Role enforcement is at three levels:

1. ``Depends(get_current_user)`` — must present a valid user JWT
2. service layer ``get_prep_for_user(order_id, user_id)`` — SELECT
   restricted to user-visible columns + ownership filter
3. ``response_model=UserPrepPackageView`` — Pydantic drops any extra
   fields the service might accidentally return

This is intentionally a separate file from the companion / admin
endpoints (rather than three handlers in one file) so a code reviewer
can ``grep`` each role's surface area independently and so that an
accidental ``include_router`` mix-up surfaces as an obvious diff.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser
from app.exceptions import NotFoundException
from app.schemas.prep_package import UserPrepPackageView

router = APIRouter(prefix="/users/orders", tags=["users-prep-package"])


@router.get(
    "/{order_id}/prep-package",
    response_model=UserPrepPackageView,
    summary="患者获取自己订单的 AI 准备包",
    description=(
        "返回完整内容: 携带物品 / 就诊前提示 / 建议询问医生的问题。"
        "仅订单归属本用户时返回; 跨订单查询返回 404 (不区分 403, 避免枚举)。"
    ),
    responses={**err(401, 404, 500)},
)
async def get_user_prep_package(
    order_id: UUID,
    current_user: CurrentUser,
) -> UserPrepPackageView:
    _ = current_user
    raise NotFoundException("Prep package service lands in S3-DEV-002-ABAC-4LAYER-PART2")
