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
4. **S3-DEV-002-PREP-API AC#3** + **S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION**:
   write a ``view_prep_package`` :class:`AdminAuditLog` row in a
   **dedicated audit session** that commits *before* the data fetch,
   so the audit trail is durable even when the service layer raises
   404 / 500. This captures admin reconnaissance attempts (probes for
   non-existent orders) in addition to successful views — closing the
   AC#3 "known limitation" from the original implementation.

   Pattern follows ``cache_invalidate.py`` (PR #250, S3-DEV-005): two
   independent FastAPI dependencies of ``get_db`` give two independent
   ``AsyncSession`` instances with separate transactions. We
   ``await audit_session.commit()`` inside the handler before the fetch
   so the audit row outlives a fetch crash / 404 / 500.

Lives under ``backend/app/api/v1/admin/`` (sub-package) so it inherits
the admin router's existing ``/admin`` prefix wiring.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.openapi_meta import err
from app.database import get_db
from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.schemas.prep_package import AdminPrepPackageView
from app.services.prep_package_service import PrepPackageService

router = APIRouter(prefix="/prep-packages", tags=["admin-prep-package"])


AuditSession = Annotated[AsyncSession, Depends(get_db)]
"""Dedicated DB session for AdminAuditLog persistence.

Reuses ``get_db`` so the test suite's ``override_get_db`` (SQLite
in-memory) and any production replicas continue to work, but FastAPI
treats this as a separate dependency from :data:`DBSession`. We get
two independent ``AsyncSession`` instances, each with its own
transaction. We ``commit`` the audit session inside the handler *before*
the data fetch so the audit row is durable even when the request
session rolls back (404 from service layer, 500 from DB, etc.).

Pattern source: ``cache_invalidate.py`` (PR #250, S3-DEV-005-CACHE-INVALIDATE).
"""


@router.get(
    "/{order_id}",
    response_model=AdminPrepPackageView,
    summary="admin 查看订单的 AI 准备包 (含 ops metadata)",
    description=(
        "返回完整内容 + ops metadata (trace_id / prompt_version_id / "
        "model / estimated/actual cost / generation_time_ms / fallback_reason)。"
        "仅 admin JWT principal 可访问 (legacy X-Admin-Token sentinel 拒绝)。"
        "**所有 admin 访问 (成功 200 / 404 不存在 / 500 异常) 均落 AdminAuditLog** "
        "(target_type=prep_package, action=view), 由 isolated AuditSession 保证 "
        "(S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION + PR #250 模式), 捕获 "
        "admin 侦察行为 (probe 不存在的 order_id)。"
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_admin_prep_package(
    order_id: UUID,
    current_admin: CurrentAdmin,
    session: DBSession,
    audit_session: AuditSession,
) -> AdminPrepPackageView:
    # AC#3 + S3-OPS-VIEW-PREP-AUDIT-ISOLATED-SESSION: write the audit
    # row in a **dedicated** session that commits *before* the data
    # fetch. This makes admin reads (including 404 probes and 500
    # crashes) auditable — closing the original AC#3 "known limitation"
    # where ``DBSession`` rollback on exception also rolled back the
    # audit row.
    #
    # Why commit before the fetch (not after):
    #   * audit row is durable even if service layer raises 404/500
    #   * captures admin reconnaissance (probes for non-existent ids)
    #   * pattern is identical to cache_invalidate.py (PR #250 lock-in)
    #
    # The two sessions are independent because they are two FastAPI
    # ``Depends(get_db)`` instances. FastAPI's dep cache keys on the
    # callable + parameter signature, not the callable identity alone
    # when the annotation differs — so ``DBSession`` and ``AuditSession``
    # resolve to two distinct sessions per request.
    audit_session.add(
        AdminAuditLog(
            target_type="prep_package",
            target_id=order_id,
            action="view",
            operator=current_admin.username,
        )
    )
    await audit_session.commit()
    return await PrepPackageService(session).get_prep_for_admin(order_id)
