from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class RegisterDeviceRequest(BaseModel):
    token: str
    device_type: str

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        allowed = {"ios", "android", "wechat"}
        if v not in allowed:
            raise ValueError(f"device_type must be one of {allowed}")
        return v


class UnregisterDeviceRequest(BaseModel):
    token: str


class DeviceTokenResponse(BaseModel):
    id: UUID
    token: str
    device_type: str
    created_at: datetime

    model_config = {"from_attributes": True}
