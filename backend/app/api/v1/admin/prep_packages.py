"""Admin-facing prep package endpoint (ABAC 4-layer, admin surface).

ADR-0048 §7.0.2 admin route. Admins see the full prep package plus ops
metadata (trace_id / prompt_version_id / model / cost / fallback_reason)
needed for AI quality audits and cost reconciliation.

Auth model:

1. ``Depends(get_current_admin)`` — JWT-only (legacy ``X-Admin-Token``
   sentinel is rejected; we need a real :class:`AdminUser` row for
   audit trails).
2. service layer ``get_prep_for_admin(order_id)`` — full SELECT, no
   ownership filter (admins see any order).
3. ``response_model=AdminPrepPackageView`` — the only view that exposes
   ops metadata.

Lives under ``backend/app/api/v1/admin/`` (sub-package) so it inherits
the admin router's existing ``/admin`` prefix wiring.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentAdmin
from app.exceptions import NotFoundException
from app.schemas.prep_package import AdminPrepPackageView

router = APIRouter(prefix="/prep-packages", tags=["admin-prep-package"])


@router.get(
    "/{order_id}",
    response_model=AdminPrepPackageView,
    summary="admin 查看订单的 AI 准备包 (含 ops metadata)",
    description=(
        "返回完整内容 + ops metadata (trace_id / prompt_version_id / "
        "model / estimated/actual cost / generation_time_ms / fallback_reason)。"
        "仅 admin JWT principal 可访问 (legacy X-Admin-Token sentinel 拒绝)。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_admin_prep_package(
    order_id: UUID,
    current_admin: CurrentAdmin,
) -> AdminPrepPackageView:
    _ = current_admin
    raise NotFoundException("Prep package service lands in S3-DEV-002-ABAC-4LAYER-PART2")
