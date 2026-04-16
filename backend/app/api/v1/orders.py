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


@router.post("", response_model=OrderResponse, status_code=201, summary="创建订单", description="患者创建陪诊服务订单，需指定服务类型、医院、预约时间等信息。")
async def create_order(
    body: CreateOrderRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.create_order(current_user, body)


@router.get("", response_model=OrderListResponse, summary="获取订单列表", description="分页查询当前用户的订单，支持按状态、日期、城市筛选。")
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


@router.get("/{order_id}", response_model=OrderResponse, summary="获取订单详情", description="根据订单ID获取订单完整信息。")
async def get_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.get_order(order_id, current_user)


@router.post("/{order_id}/accept", response_model=OrderResponse, summary="接受订单", description="陪诊师接受指定订单，订单状态变为已接单。")
async def accept_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.accept_order(order_id, current_user)


@router.post("/{order_id}/start", response_model=OrderResponse, summary="开始服务", description="陪诊师开始执行陪诊服务，订单状态变为进行中。")
async def start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.start_order(order_id, current_user)


@router.post("/{order_id}/request-start", response_model=OrderResponse, summary="请求开始服务", description="陪诊师发起开始服务请求，等待患者确认。")
async def request_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.request_start_service(order_id, current_user)


@router.post("/{order_id}/confirm-start", response_model=OrderResponse, summary="确认开始服务", description="患者确认陪诊师的开始服务请求，订单正式进入服务中状态。")
async def confirm_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.confirm_start_service(order_id, current_user)


@router.post("/{order_id}/complete", response_model=OrderResponse, summary="完成订单", description="陪诊师标记订单服务已完成。")
async def complete_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.complete_order(order_id, current_user)


@router.post("/{order_id}/reject", response_model=OrderResponse, summary="拒绝订单", description="陪诊师拒绝指定订单，已支付订单将自动退款。")
async def reject_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.reject_order(order_id, current_user)


@router.post("/{order_id}/cancel", response_model=OrderResponse, summary="取消订单", description="取消指定订单，可在多个状态下操作，已支付订单将触发退款。")
async def cancel_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.cancel_order(order_id, current_user)


@router.post("/{order_id}/pay", summary="支付订单", description="对指定订单发起支付，返回支付参数。MVP阶段为模拟支付。")
async def pay_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    result = await service.pay_order(order_id, current_user)
    return {
        "payment_id": str(result.payment_id),
        "provider": result.provider,
        "prepay_id": result.prepay_id,
        "sign_params": result.sign_params,
        "mock_success": result.mock_success,
    }


@router.post("/{order_id}/refund", response_model=PaymentResponse, summary="申请退款", description="对已支付的订单申请退款，退款金额原路返回。")
async def refund_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.refund_order(order_id, current_user)


@router.post("/check-expired", summary="检查过期订单", description="扫描并自动取消超时未接单的订单，可由定时任务调用。")
async def check_expired_orders(
    session: DBSession,
):
    service = OrderService(session)
    cancelled = await service.check_expired_orders()
    return {"cancelled_count": len(cancelled), "cancelled_order_ids": [str(o.id) for o in cancelled]}
