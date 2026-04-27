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

from app.api.v1.admin.companions import router as companions_router
from app.api.v1.admin.orders import router as orders_router
from app.api.v1.admin.users import router as users_router

router = APIRouter(prefix="/admin", tags=["admin"])

router.include_router(companions_router)
router.include_router(orders_router)
router.include_router(users_router)
