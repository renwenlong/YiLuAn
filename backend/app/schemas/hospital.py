from uuid import UUID

from pydantic import BaseModel


class HospitalResponse(BaseModel):
    id: UUID
    name: str
    address: str | None = None
    level: str | None = None
    province: str | None = None
    city: str | None = None
    district: str | None = None
    tags: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    model_config = {"from_attributes": True}


class HospitalListResponse(BaseModel):
    items: list[HospitalResponse]
    total: int


class HospitalFiltersResponse(BaseModel):
    provinces: list[str]
    cities: list[str]
    districts: list[str]
    levels: list[str]
    tags: list[str]


class HospitalRegionResponse(BaseModel):
    province: str | None = None
    city: str | None = None
