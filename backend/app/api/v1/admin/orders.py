"""
Admin Orders — order management (B4).

Routes: /api/v1/admin/orders
Auth: X-Admin-Token header (token-based; v2 will migrate to JWT).

Endpoints
---------
GET    /                        list orders, filters: status / patient_id /
                                companion_id / date_from / date_to
GET    /{order_id}              order detail
POST   /{order_id}/force-status body {status, reason} — manual override
POST   /{order_id}/refund       body {amount, reason} — admin refund

All mutating endpoints write an ``AdminAuditLog`` row.
"""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.admin_auth import require_admin_token
from app.dependencies import DBSession
from app.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.order import Order, OrderStatus
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository
from app.services.payment_service import PaymentService

router = APIRouter(
    prefix="/orders",
    tags=["admin-orders"],
    dependencies=[Depends(require_admin_token)],
)


# Statuses for which a refund may be initiated. Aligns with the contract
# in docs/admin-mvp-scope.md (B4) — order must already have a successful
# pay-side Payment row, which only exists after the order moves out of
# ``created``.
REFUNDABLE_STATUSES: set[OrderStatus] = {
    OrderStatus.accepted,
    OrderStatus.in_progress,
    OrderStatus.completed,
    OrderStatus.reviewed,
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OrderItem(BaseModel):
    id: str = Field(..., description="订单 UUID")
    order_number: str = Field(..., description="订单号")
    patient_id: str = Field(..., description="患者 UUID")
    companion_id: str | None = Field(None, description="陪诊师 UUID")
    hospital_id: str = Field(..., description="医院 UUID")
    status: str = Field(..., description="订单状态")
    appointment_date: str = Field(..., description="预约日期 YYYY-MM-DD")
    appointment_time: str = Field(..., description="预约时间 HH:MM")
    price: str = Field(..., description="订单金额（元，字符串保两位小数）")
    created_at: str | None = Field(None, description="创建时间 ISO8601")


class PaginatedOrders(BaseModel):
    items: list[OrderItem]
    total: int
    page: int
    page_size: int


class ForceStatusBody(BaseModel):
    status: str = Field(..., description="目标状态值（OrderStatus 之一）")
    reason: str = Field(..., min_length=1, max_length=500, description="操作原因")


class RefundBody(BaseModel):
    amount: Decimal = Field(..., gt=0, description="退款金额（元）")
    reason: str = Field(..., min_length=1, max_length=500, description="退款原因")


class ForceStatusResponse(BaseModel):
    order_id: str
    old_status: str
    new_status: str


class RefundResponse(BaseModel):
    order_id: str
    refund_amount: str
    refund_id: str | None
    payment_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item(o: Order) -> dict:
    return {
        "id": str(o.id),
        "order_number": o.order_number,
        "patient_id": str(o.patient_id),
        "companion_id": str(o.companion_id) if o.companion_id else None,
        "hospital_id": str(o.hospital_id),
        "status": o.status.value,
        "appointment_date": o.appointment_date,
        "appointment_time": o.appointment_time,
        "price": str(Decimal(str(o.price)).quantize(Decimal("0.01"))),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedOrders,
    summary="后台：订单列表",
    description="按状态 / 患者 / 陪诊师 / 预约日期范围分页查询订单。",
)
async def list_orders(
    session: DBSession,
    status: str | None = Query(None, description="OrderStatus 之一"),
    patient_id: UUID | None = Query(None),
    companion_id: UUID | None = Query(None),
    date_from: str | None = Query(None, description="预约开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="预约结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repo = OrderRepository(session)
    skip = (page - 1) * page_size
    order_status: OrderStatus | None
    if status:
        try:
            order_status = OrderStatus(status)
        except ValueError as exc:
            raise BadRequestException(f"Invalid status: {status}") from exc
    else:
        order_status = None

    items, total = await repo.list_all(
        status=order_status,
        patient_id=patient_id,
        companion_id=companion_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=page_size,
    )
    return {
        "items": [_to_item(o) for o in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{order_id}",
    response_model=OrderItem,
    summary="后台：订单详情",
)
async def get_order(order_id: UUID, session: DBSession):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")
    return _to_item(order)


@router.post(
    "/{order_id}/force-status",
    response_model=ForceStatusResponse,
    summary="后台：强制修改订单状态",
    description=(
        "管理员手动覆盖订单状态，**绕过业务状态机**，仅用于运营干预。"
        " 必须提供原因，操作记录会写入 admin_audit_log。"
    ),
)
async def force_order_status(
    order_id: UUID,
    body: ForceStatusBody,
    session: DBSession,
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    try:
        new_status = OrderStatus(body.status)
    except ValueError as exc:
        raise BadRequestException(f"Invalid status: {body.status}") from exc

    old_status = order.status
    order.status = new_status

    log = AdminAuditLog(
        target_type="order",
        target_id=order_id,
        action="force_status",
        operator="admin-token",
        reason=f"{old_status.value}->{new_status.value}: {body.reason}",
    )
    session.add(log)
    await session.flush()

    return {
        "order_id": str(order_id),
        "old_status": old_status.value,
        "new_status": new_status.value,
    }


@router.post(
    "/{order_id}/refund",
    response_model=RefundResponse,
    summary="后台：管理员退款",
    description=(
        "管理员发起退款。约束："
        " (1) 订单状态需为 accepted / in_progress / completed / reviewed；"
        " (2) 退款金额 ≤ 已支付金额；"
        " (3) 同一订单已存在 success 退款时拒绝（依赖 PaymentService 唯一约束）。"
    ),
)
async def refund_order(
    order_id: UUID,
    body: RefundBody,
    session: DBSession,
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    if order.status not in REFUNDABLE_STATUSES:
        raise BadRequestException(
            f"Order status '{order.status.value}' is not refundable"
        )

    pay_repo = PaymentRepository(session)
    original_pay = await pay_repo.get_by_order_and_type(order_id, "pay")
    if original_pay is None or original_pay.status != "success":
        raise BadRequestException("原订单未支付成功，无法退款")

    try:
        refund_amount = Decimal(body.amount).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise BadRequestException("Invalid refund amount") from exc

    paid_amount = Decimal(str(original_pay.amount)).quantize(Decimal("0.01"))
    if refund_amount > paid_amount:
        raise BadRequestException(
            f"退款金额 {refund_amount} 超过原支付金额 {paid_amount}"
        )

    payment_svc = PaymentService(session)
    result = await payment_svc.create_refund(
        order_id=order_id,
        user_id=order.patient_id,
        original_amount=paid_amount,
        refund_amount=refund_amount,
    )

    log = AdminAuditLog(
        target_type="order",
        target_id=order_id,
        action="refund",
        operator="admin-token",
        reason=f"amount={refund_amount}: {body.reason}",
    )
    session.add(log)
    await session.flush()

    return {
        "order_id": str(order_id),
        "refund_amount": str(refund_amount),
        "refund_id": result.refund_id,
        "payment_id": str(result.payment_id),
    }
