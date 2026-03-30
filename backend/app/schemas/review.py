from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5)
    content: str = Field(..., min_length=5, max_length=500)


class ReviewResponse(BaseModel):
    id: UUID
    order_id: UUID
    patient_id: UUID
    companion_id: UUID
    rating: int
    content: str | None = None
    patient_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse]
    total: int
