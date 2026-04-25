from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.review import (
    CreateReviewRequest,
    ReviewListResponse,
    ReviewResponse,
)
from app.services.review import ReviewService

router = APIRouter(tags=["reviews"])


@router.post(
    "/orders/{order_id}/review",
    response_model=ReviewResponse,
    status_code=201,
    summary="提交订单评价",
    description=(
        "患者在订单 `completed` 后提交评价：1~5 星评分 + 5~500 字评论。"
        "**单订单仅可评价一次**，重复提交将返回 400。"
    ),
    responses={**err(400, 401, 403, 404, 422, 500)},
)
async def submit_review(
    order_id: UUID,
    body: CreateReviewRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ReviewService(session)
    return await service.submit_review(order_id, current_user, body)


@router.get(
    "/orders/{order_id}/review",
    response_model=ReviewResponse,
    summary="查看订单评价",
    description="查看指定订单的评价。若订单未被评价，返回 404。",
    responses={**err(401, 404, 500)},
)
async def get_review(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ReviewService(session)
    return await service.get_review(order_id)


@router.get(
    "/companions/{companion_id}/reviews",
    response_model=ReviewListResponse,
    summary="陪诊师收到的评价列表",
    description="分页查询某位陪诊师收到的全部评价（公开数据，用于详情页展示）。",
    responses={**err(401, 404, 500)},
)
async def list_companion_reviews(
    companion_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = ReviewService(session)
    items, total = await service.list_companion_reviews(
        companion_id, page=page, page_size=page_size
    )
    return ReviewListResponse(
        items=[ReviewResponse.model_validate(r) for r in items],
        total=total,
    )
