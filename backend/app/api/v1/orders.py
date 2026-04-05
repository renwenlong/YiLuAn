from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.order import (
    CreateOrderRequest,
    OrderListResponse,
    OrderResponse,
    PaymentResponse,
)
from app.services.order import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("", response_model=OrderResponse, status_code=201)
async def create_order(
    body: CreateOrderRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.create_order(current_user, body)


@router.get("", response_model=OrderListResponse)
async def list_orders(
    current_user: CurrentUser,
    session: DBSession,
    status: str | None = Query(None),
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    city: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = OrderService(session)
    items, total = await service.list_orders(
        current_user, status=status, date=date, city=city, page=page, page_size=page_size
    )
    return OrderListResponse(
        items=[OrderResponse.model_validate(o) for o in items],
        total=total,
    )


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.get_order(order_id, current_user)


@router.post("/{order_id}/accept", response_model=OrderResponse)
async def accept_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.accept_order(order_id, current_user)


@router.post("/{order_id}/start", response_model=OrderResponse)
async def start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.start_order(order_id, current_user)


@router.post("/{order_id}/request-start", response_model=OrderResponse)
async def request_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.request_start_service(order_id, current_user)


@router.post("/{order_id}/confirm-start", response_model=OrderResponse)
async def confirm_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.confirm_start_service(order_id, current_user)


@router.post("/{order_id}/complete", response_model=OrderResponse)
async def complete_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.complete_order(order_id, current_user)


@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.cancel_order(order_id, current_user)


@router.post("/{order_id}/pay", response_model=PaymentResponse)
async def pay_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.pay_order(order_id, current_user)


@router.post("/{order_id}/refund", response_model=PaymentResponse)
async def refund_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.refund_order(order_id, current_user)
