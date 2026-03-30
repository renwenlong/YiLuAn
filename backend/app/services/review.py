import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.user import User, UserRole
from app.repositories.order import OrderRepository
from app.repositories.review import ReviewRepository
from app.schemas.review import CreateReviewRequest


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.review_repo = ReviewRepository(session)
        self.order_repo = OrderRepository(session)
        self.session = session

    async def submit_review(
        self, order_id: uuid.UUID, user: User, data: CreateReviewRequest
    ) -> Review:
        order = await self.order_repo.get_by_id(order_id)
        if order is None:
            raise NotFoundException("Order not found")
        if order.patient_id != user.id:
            raise ForbiddenException("Only the patient can review this order")
        if order.status != OrderStatus.completed:
            raise BadRequestException("Order must be completed before review")

        existing = await self.review_repo.get_by_order_id(order_id)
        if existing is not None:
            raise BadRequestException("Order already reviewed")

        if order.companion_id is None:
            raise BadRequestException("Order has no companion to review")

        review = Review(
            order_id=order_id,
            patient_id=user.id,
            companion_id=order.companion_id,
            rating=data.rating,
            content=data.content,
            patient_name=user.display_name or user.phone,
        )
        review = await self.review_repo.create(review)

        # Transition order to reviewed
        await self.order_repo.update(order, {"status": OrderStatus.reviewed})
        return review

    async def get_review(self, order_id: uuid.UUID) -> Review:
        review = await self.review_repo.get_by_order_id(order_id)
        if review is None:
            raise NotFoundException("Review not found")
        return review

    async def list_companion_reviews(
        self,
        companion_id: uuid.UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list, int]:
        skip = (page - 1) * page_size
        return await self.review_repo.list_by_companion(
            companion_id, skip=skip, limit=page_size
        )
