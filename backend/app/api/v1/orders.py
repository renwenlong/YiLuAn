from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.v1.openapi_meta import err
from app.core.admin_auth import require_admin_token
from app.dependencies import CurrentUser, DBSession
from app.schemas.order import (
    CreateOrderRequest,
    OrderListResponse,
    OrderResponse,
    PaymentResponse,
)
from app.services.order import OrderService

router = APIRouter(prefix="/orders", tags=["orders"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=201,
    summary="患者创建订单",
    description=(
        "患者发起一笔陪诊服务订单。需指定服务类型、医院、就诊日期与时间。"
        "可选 `companion_id` 直接指派，否则进入大厅由陪诊师抢单。\n\n"
        "新订单状态为 `pending_payment`，**必须在 30 分钟内完成支付**，否则会被定时任务自动取消。"
    ),
    responses={**err(400, 401, 422, 500)},
)
async def create_order(
    body: CreateOrderRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.create_order(current_user, body)


@router.get(
    "",
    response_model=OrderListResponse,
    summary="获取我的订单列表",
    description="分页查询当前用户参与的订单（患者视角看自己创建的，陪诊师视角看自己接的）。",
    responses={**err(401, 422, 500)},
)
async def list_orders(
    current_user: CurrentUser,
    session: DBSession,
    status: str | None = Query(None, description="订单状态过滤"),
    date: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="预约日期 YYYY-MM-DD"),
    city: str | None = Query(None, description="按城市过滤"),
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


@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    summary="获取订单详情",
    description="按订单 ID 获取详情。仅订单参与方与管理员可见。",
    responses={**err(401, 403, 404, 500)},
)
async def get_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.get_order(order_id, current_user)


@router.post(
    "/{order_id}/accept",
    response_model=OrderResponse,
    summary="陪诊师接单",
    description="陪诊师接受指定订单。需订单处于 `paid` 且未被其他陪诊师接走。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def accept_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.accept_order(order_id, current_user)


@router.post(
    "/{order_id}/start",
    response_model=OrderResponse,
    summary="陪诊师直接开始服务",
    description="陪诊师标记开始服务（已与患者线下见面），订单进入 `in_service`。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.start_order(order_id, current_user)


@router.post(
    "/{order_id}/request-start",
    response_model=OrderResponse,
    summary="陪诊师发起开始服务请求",
    description="陪诊师发起「开始服务」请求，等待患者在 App 内确认（双确认流程）。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def request_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.request_start_service(order_id, current_user)


@router.post(
    "/{order_id}/confirm-start",
    response_model=OrderResponse,
    summary="患者确认开始服务",
    description="患者确认陪诊师的开始服务请求，订单正式进入 `in_service` 状态。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def confirm_start_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.confirm_start_service(order_id, current_user)


@router.post(
    "/{order_id}/complete",
    response_model=OrderResponse,
    summary="完成订单",
    description="陪诊师标记订单服务已完成，订单进入 `completed`，触发评价流程。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def complete_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.complete_order(order_id, current_user)


@router.post(
    "/{order_id}/reject",
    response_model=OrderResponse,
    summary="陪诊师拒单",
    description="陪诊师拒绝指定订单。若已支付，则自动触发全额退款。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def reject_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.reject_order(order_id, current_user)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderResponse,
    summary="取消订单",
    description=(
        "取消指定订单。患者和陪诊师均可在不同状态下调用，"
        "已支付订单将按规则触发退款（详见钱包/退款规则文档）。"
    ),
    responses={**err(400, 401, 403, 404, 500)},
)
async def cancel_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.cancel_order(order_id, current_user)


@router.post(
    "/{order_id}/pay",
    summary="对订单发起支付",
    description=(
        "对指定订单发起支付，返回前端调起微信支付所需的参数。"
        "MVP 环境下使用 mock provider，会直接返回 `mock_success=true`。"
    ),
    responses={
        200: {
            "description": "支付参数",
            "content": {
                "application/json": {
                    "example": {
                        "payment_id": "ec3a0d74-...-...",
                        "provider": "wechat",
                        "prepay_id": "wx2025...",
                        "sign_params": {"appId": "wx...", "timeStamp": "1700000000", "nonceStr": "abcd", "package": "prepay_id=wx...", "signType": "RSA", "paySign": "..."},
                        "mock_success": False,
                    }
                }
            },
        },
        **err(400, 401, 403, 404, 500),
    },
)
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


@router.post(
    "/{order_id}/refund",
    response_model=PaymentResponse,
    summary="患者申请退款",
    description="对已支付订单申请退款，金额原路返回到支付账户。",
    responses={**err(400, 401, 403, 404, 500)},
)
async def refund_order(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = OrderService(session)
    return await service.refund_order(order_id, current_user)


@router.post(
    "/check-expired",
    summary="扫描并取消过期订单（运维/定时任务）",
    description=(
        "扫描所有 `pending_payment` 超过 30 分钟未支付的订单并自动取消。"
        "由内部定时任务调度，**需 `X-Admin-Token` 鉴权**。"
    ),
    dependencies=[Depends(require_admin_token)],
    responses={
        200: {
            "description": "执行结果",
            "content": {
                "application/json": {
                    "example": {"cancelled_count": 3, "cancelled_order_ids": ["uuid1", "uuid2", "uuid3"]}
                }
            },
        },
        **err(401, 403, 500),
    },
)
async def check_expired_orders(
    session: DBSession,
):
    service = OrderService(session)
    cancelled = await service.check_expired_orders()
    return {"cancelled_count": len(cancelled), "cancelled_order_ids": [str(o.id) for o in cancelled]}
