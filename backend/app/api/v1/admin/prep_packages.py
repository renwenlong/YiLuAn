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
4. **S3-DEV-002-PREP-API AC#3**: write a ``view_prep_package``
   :class:`AdminAuditLog` row before returning so the admin's view of
   sensitive medical context is reconcilable.  We write *unconditionally*
   (even when the underlying package is missing → 404) because **the
   attempt to view is itself auditable** (knowing someone probed an
   order's prep package is forensic-relevant).

Lives under ``backend/app/api/v1/admin/`` (sub-package) so it inherits
the admin router's existing ``/admin`` prefix wiring.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.schemas.prep_package import AdminPrepPackageView
from app.services.prep_package_service import PrepPackageService

router = APIRouter(prefix="/prep-packages", tags=["admin-prep-package"])


@router.get(
    "/{order_id}",
    response_model=AdminPrepPackageView,
    summary="admin 查看订单的 AI 准备包 (含 ops metadata)",
    description=(
        "返回完整内容 + ops metadata (trace_id / prompt_version_id / "
        "model / estimated/actual cost / generation_time_ms / fallback_reason)。"
        "仅 admin JWT principal 可访问 (legacy X-Admin-Token sentinel 拒绝)。"
        "每次调用写入 AdminAuditLog (target_type=prep_package, action=view)."
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_admin_prep_package(
    order_id: UUID,
    current_admin: CurrentAdmin,
    session: DBSession,
) -> AdminPrepPackageView:
    # AC#3: write audit log *before* the data fetch.
    # Why before:
    #  * even a 404/500 attempt must be auditable (was someone probing?)
    #  * the audit row is small, the fetch is the costly part — if we wrote
    #    after, a fetch error would lose the audit trace
    #  * if audit insert itself fails, the request should also fail; the
    #    admin's "I viewed this" claim is only meaningful when persisted
    audit = AdminAuditLog(
        target_type="prep_package",
        target_id=order_id,
        action="view",
        operator=current_admin.username,
    )
    session.add(audit)
    await session.flush()
    return await PrepPackageService(session).get_prep_for_admin(order_id)
