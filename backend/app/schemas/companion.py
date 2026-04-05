from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplyCompanionRequest(BaseModel):
    real_name: str = Field(..., min_length=2, max_length=50)
    id_number: str | None = None
    certifications: str | None = None
    service_area: str | None = None
    service_types: str = Field(..., min_length=1, max_length=200)
    service_hospitals: str | None = None
    service_city: str | None = None
    bio: str | None = None


class UpdateCompanionProfileRequest(BaseModel):
    service_area: str | None = None
    service_types: str | None = None
    bio: str | None = None
    certifications: str | None = None
    service_hospitals: str | None = None
    service_city: str | None = None


class CompanionListResponse(BaseModel):
    id: UUID
    user_id: UUID
    real_name: str
    service_area: str | None = None
    service_types: str | None = None
    service_hospitals: str | None = None
    service_city: str | None = None
    bio: str | None = None
    avg_rating: float = 0.0
    total_orders: int = 0
    verification_status: str = "pending"

    model_config = {"from_attributes": True}


class CompanionDetailResponse(CompanionListResponse):
    certifications: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanionStatsResponse(BaseModel):
    open_orders: int = 0
    total_orders: int = 0
    avg_rating: float = 0.0
    total_earnings: float = 0.0
