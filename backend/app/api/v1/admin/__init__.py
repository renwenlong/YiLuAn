"""
Admin API — platform operations MVP.

Covers:
  - Companion verification (approve / reject)
  - Order management (query / force-status / refund)
  - User management (disable / enable)

All endpoints require admin role (enforced by get_admin_user dependency).
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import DBSession, get_current_user
from app.exceptions import ForbiddenException, NotFoundException, BadRequestException
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.repositories.order import OrderRepository
from app.repositories.user import UserRepository
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/admin", tags=["admin"])


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """Require admin role for all admin endpoints."""
    if not current_user.has_role("admin"):
        raise ForbiddenException("Admin access required")
    return current_user


AdminUser = get_admin_user



# =============================================================================
# Order Management
# =============================================================================


@router.get("/orders")
async def list_orders_admin(
    session: DBSession,
    _admin: User = Depends(AdminUser),
    status: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Query all orders with optional status filter."""
    repo = OrderRepository(session)
    skip = (page - 1) * page_size
    order_status = OrderStatus(status) if status else None
    items, total = await repo.list_all(
        status=order_status, skip=skip, limit=page_size
    )
    return {"items": items, "total": total, "page": page}


@router.post("/orders/{order_id}/force-status")
async def force_order_status(
    order_id: UUID,
    session: DBSession,
    target_status: str = Query(...),
    _admin: User = Depends(AdminUser),
):
    """Force an order to a specific status (admin override)."""
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    try:
        new_status = OrderStatus(target_status)
    except ValueError:
        raise BadRequestException(f"Invalid status: {target_status}")

    old_status = order.status
    order.status = new_status
    await session.flush()
    return {
        "order_id": str(order_id),
        "old_status": old_status.value,
        "new_status": new_status.value,
    }


@router.post("/orders/{order_id}/admin-refund")
async def admin_refund_order(
    order_id: UUID,
    session: DBSession,
    _admin: User = Depends(AdminUser),
    refund_ratio: float = Query(1.0, ge=0, le=1),
):
    """Admin-initiated refund with configurable ratio."""
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    payment_svc = PaymentService(session)
    refund_amount = round(order.price * refund_ratio, 2)

    try:
        result = await payment_svc.create_refund(
            order_id=order_id,
            user_id=order.patient_id,
            original_amount=order.price,
            refund_amount=refund_amount,
        )
    except BadRequestException:
        raise BadRequestException("Refund failed — order may already be refunded or unpaid")

    return {
        "order_id": str(order_id),
        "refund_amount": refund_amount,
        "refund_id": str(result.payment_id),
    }


# =============================================================================
# User Management
# =============================================================================


@router.get("/users")
async def list_users_admin(
    session: DBSession,
    _admin: User = Depends(AdminUser),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List all users."""
    repo = UserRepository(session)
    skip = (page - 1) * page_size
    users, total = await repo.list_all(skip=skip, limit=page_size)
    return {"items": users, "total": total, "page": page}


@router.post("/users/{user_id}/disable")
async def disable_user(
    user_id: UUID,
    session: DBSession,
    _admin: User = Depends(AdminUser),
):
    """Disable a user account."""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")
    user.is_active = False
    await session.flush()
    return {"user_id": str(user_id), "is_active": False}


@router.post("/users/{user_id}/enable")
async def enable_user(
    user_id: UUID,
    session: DBSession,
    _admin: User = Depends(AdminUser),
):
    """Re-enable a disabled user account."""
    repo = UserRepository(session)
    user = await repo.get_by_id(user_id)
    if user is None:
        raise NotFoundException("User not found")
    user.is_active = True
    await session.flush()
    return {"user_id": str(user_id), "is_active": True}


# ---------------------------------------------------------------------------
# Sub-module routers (A6)
# ---------------------------------------------------------------------------
from app.api.v1.admin.companions import router as companions_router  # noqa: E402

router.include_router(companions_router)
