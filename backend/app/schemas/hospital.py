from uuid import UUID

from pydantic import BaseModel


class HospitalResponse(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    level: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"from_attributes": True}


class HospitalListResponse(BaseModel):
    items: list[HospitalResponse]
    total: int
