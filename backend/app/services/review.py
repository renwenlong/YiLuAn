import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.order import Order, OrderStatus
from app.models.review import Review
from app.models.user import User, UserRole
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.order import OrderRepository
from app.repositories.review import ReviewRepository
from app.schemas.review import CreateReviewRequest
from app.services.notification import NotificationService


class ReviewService:
    def __init__(self, session: AsyncSession):
        self.review_repo = ReviewRepository(session)
        self.order_repo = OrderRepository(session)
        self.companion_repo = CompanionProfileRepository(session)
        self.notification_svc = NotificationService(session)
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

        # F-04: resolve 4 dimension ratings + total. Backward compatible:
        #  - if any dimension provided => all 4 must be provided (validated in schema)
        #  - if only legacy `rating` provided => fan out to 4 dimensions
        if data.punctuality_rating is not None:
            punctuality = data.punctuality_rating
            professionalism = data.professionalism_rating
            communication = data.communication_rating
            attitude = data.attitude_rating
        else:
            assert data.rating is not None  # schema enforces this
            punctuality = professionalism = communication = attitude = data.rating

        weighted = (
            punctuality * settings.review_weight_punctuality
            + professionalism * settings.review_weight_professionalism
            + communication * settings.review_weight_communication
            + attitude * settings.review_weight_attitude
        )
        # Round to nearest int (1~5) to keep `rating` column an integer and
        # keep legacy contract intact.
        total_rating = max(1, min(5, int(round(weighted))))

        review = Review(
            order_id=order_id,
            patient_id=user.id,
            companion_id=order.companion_id,
            rating=total_rating,
            punctuality_rating=punctuality,
            professionalism_rating=professionalism,
            communication_rating=communication,
            attitude_rating=attitude,
            content=data.content,
            patient_name=user.display_name or user.phone,
        )
        review = await self.review_repo.create(review)

        # Transition order to reviewed
        await self.order_repo.update(order, {"status": OrderStatus.reviewed})

        # Update companion avg_rating on profile (create profile if missing)
        profile = await self.companion_repo.get_by_user_id(order.companion_id)
        avg = await self.review_repo.get_companion_avg_rating(order.companion_id)
        if profile:
            await self.companion_repo.update(
                profile,
                {
                    "avg_rating": avg,
                    "total_orders": profile.total_orders + 1,
                },
            )
        else:
            # Companion registered without profile — create a minimal one
            companion_user = await self.order_repo.session.get(User, order.companion_id)
            fallback_name = (
                companion_user.display_name or companion_user.phone
                if companion_user
                else "未知"
            )
            from app.models.companion_profile import CompanionProfile

            new_profile = CompanionProfile(
                user_id=order.companion_id,
                real_name=fallback_name,
                avg_rating=avg,
                total_orders=1,
            )
            await self.companion_repo.create(new_profile)

        # Notify companion about the review
        await self.notification_svc.notify_review_received(
            companion_id=order.companion_id,
            patient_name=user.display_name or user.phone,
            order_id=order_id,
            rating=total_rating,
            review_id=review.id,
        )

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
