from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.review import (
    CreateReviewRequest,
    ReviewListResponse,
    ReviewResponse,
)
from app.services.review import ReviewService

router = APIRouter(tags=["reviews"])


@router.post("/orders/{order_id}/review", response_model=ReviewResponse, status_code=201, summary="提交评价", description="患者对已完成的订单提交评价，包括评分和文字评论。")
async def submit_review(
    order_id: UUID,
    body: CreateReviewRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ReviewService(session)
    return await service.submit_review(order_id, current_user, body)


@router.get("/orders/{order_id}/review", response_model=ReviewResponse, summary="获取订单评价", description="获取指定订单的评价详情。")
async def get_review(
    order_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    service = ReviewService(session)
    return await service.get_review(order_id)


@router.get("/companions/{companion_id}/reviews", response_model=ReviewListResponse, summary="获取陪诊师评价列表", description="分页查询指定陪诊师收到的所有评价。")
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
