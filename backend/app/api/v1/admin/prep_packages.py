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
   sensitive medical context is reconcilable.

   We write the audit row *before* the data fetch (not after) so a
   successful view always has an audit trace ahead of the heavy I/O.
   However, the audit row shares the request-scoped transaction with
   the fetch, so a 404 / 500 from the service layer rolls back both —
   probe attempts against non-existent orders are **not** captured.
   Auditing reconnaissance is a stronger property that would need a
   second commit boundary; tracked as a follow-up (separate ADR) and
   intentionally out of scope for AC#3.

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
        "成功返回时写入 AdminAuditLog (target_type=prep_package, action=view); "
        "404/500 因事务回滚不留 audit (probe 审计是后续 ADR 范围)。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_admin_prep_package(
    order_id: UUID,
    current_admin: CurrentAdmin,
    session: DBSession,
) -> AdminPrepPackageView:
    # AC#3: write audit log *before* the data fetch.
    # Why before (not after):
    #  * a successful view always lands an audit row ahead of the heavy I/O,
    #    so a fetch crash mid-flight doesn't lose the audit trace
    #  * the audit insert is cheap, the fetch is the costly part
    #  * if audit insert itself fails, the request should also fail; the
    #    admin's "I viewed this" claim is only meaningful when persisted
    #
    # Known limitation: the audit row shares this request's transaction with
    # the fetch, so a 404/500 from the service layer rolls back both. Probe
    # attempts (admin GETs an order id that does not exist) are NOT audited.
    # Capturing reconnaissance needs a second commit boundary — separate ADR,
    # tracked as follow-up, intentionally out of scope for AC#3.
    audit = AdminAuditLog(
        target_type="prep_package",
        target_id=order_id,
        action="view",
        operator=current_admin.username,
    )
    session.add(audit)
    await session.flush()
    return await PrepPackageService(session).get_prep_for_admin(order_id)
