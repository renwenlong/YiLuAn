"""
Admin API root — platform operations MVP (B4).

Sub-routers:
  - companions (B1)  — verification workflow
  - orders     (B4)  — order list / force-status / refund
  - users      (B4)  — user list / disable / enable

All endpoints require the ``X-Admin-Token`` header (token-based admin
auth, see :mod:`app.core.admin_auth`). JWT/OAuth admin login is tracked
as the v2 follow-up (see ``docs/admin-mvp-scope.md``).
"""

from fastapi import APIRouter

from app.api.v1.admin.ai_blocklist import router as admin_ai_blocklist_router
from app.api.v1.admin.audit_logs import router as audit_logs_router
from app.api.v1.admin.auth import router as auth_router
from app.api.v1.admin.cache_invalidate import router as admin_cache_router
from app.api.v1.admin.companions import (
    public_certification_images_router,
)
from app.api.v1.admin.companions import (
    router as companions_router,
)
from app.api.v1.admin.contracts import router as admin_contracts_router
from app.api.v1.admin.dashboard import router as dashboard_router
from app.api.v1.admin.dead_letters import router as dead_letters_router
from app.api.v1.admin.feedbacks import router as admin_feedbacks_router
from app.api.v1.admin.notes import (
    notes_router as admin_notes_router,
)
from app.api.v1.admin.notes import (
    timeline_router as admin_order_timeline_router,
)
from app.api.v1.admin.orders import router as orders_router
from app.api.v1.admin.prep_packages import router as admin_prep_packages_router
from app.api.v1.admin.readonly_gate import router as readonly_gate_router
from app.api.v1.admin.reconciliation import router as reconciliation_router
from app.api.v1.admin.service_packages import router as service_packages_router
from app.api.v1.admin.telemetry import router as telemetry_router
from app.api.v1.admin.users import router as users_router
from app.api.v1.admin.wallet_ledger import router as wallet_ledger_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(audit_logs_router)
router.include_router(public_certification_images_router)
router.include_router(companions_router)
router.include_router(admin_contracts_router)
router.include_router(admin_ai_blocklist_router)
router.include_router(admin_cache_router)
router.include_router(orders_router)
router.include_router(admin_order_timeline_router)
router.include_router(admin_notes_router)
router.include_router(admin_prep_packages_router)
router.include_router(admin_feedbacks_router)
router.include_router(reconciliation_router)
router.include_router(service_packages_router)
router.include_router(telemetry_router)
router.include_router(users_router)
router.include_router(wallet_ledger_router)
router.include_router(dead_letters_router)
router.include_router(readonly_gate_router)
