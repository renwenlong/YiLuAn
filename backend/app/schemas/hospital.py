from uuid import UUID

from pydantic import BaseModel, Field


class HospitalResponse(BaseModel):
    id: UUID = Field(..., description="医院 UUID")
    name: str = Field(..., description="医院名称", examples=["北京协和医院"])
    address: str | None = Field(None, description="详细地址", examples=["东城区帅府园1号"])
    level: str | None = Field(None, description="医院等级", examples=["三甲"])
    province: str | None = Field(None, description="省份", examples=["北京"])
    city: str | None = Field(None, description="城市", examples=["北京"])
    district: str | None = Field(None, description="区县", examples=["东城区"])
    tags: str | None = Field(None, description="标签，逗号分隔", examples=["综合,教学"])
    latitude: float | None = Field(None, description="纬度")
    longitude: float | None = Field(None, description="经度")

    model_config = {"from_attributes": True}


class HospitalListResponse(BaseModel):
    items: list[HospitalResponse] = Field(..., description="当页医院列表")
    total: int = Field(..., description="总条数")


class HospitalFiltersResponse(BaseModel):
    provinces: list[str] = Field(..., description="可选省份列表")
    cities: list[str] = Field(..., description="可选城市列表")
    districts: list[str] = Field(..., description="可选区县列表")
    levels: list[str] = Field(..., description="可选医院等级")
    tags: list[str] = Field(..., description="可选标签")


class HospitalRegionResponse(BaseModel):
    province: str | None = Field(None, description="最近的省份", examples=["北京"])
    city: str | None = Field(None, description="最近的城市", examples=["北京"])
