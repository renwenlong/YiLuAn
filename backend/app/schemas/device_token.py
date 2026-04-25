from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class RegisterDeviceRequest(BaseModel):
    token: str = Field(..., description="设备推送 token（APNs/FCM/微信 OpenID）", examples=["fcm-xxx-yyy-zzz"])
    device_type: str = Field(..., description="设备类型：ios / android / wechat", examples=["ios"])

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: str) -> str:
        allowed = {"ios", "android", "wechat"}
        if v not in allowed:
            raise ValueError(f"device_type must be one of {allowed}")
        return v


class UnregisterDeviceRequest(BaseModel):
    token: str = Field(..., description="待注销的设备 token")


class DeviceTokenResponse(BaseModel):
    id: UUID = Field(..., description="记录 ID")
    token: str = Field(..., description="设备推送 token")
    device_type: str = Field(..., description="设备类型")
    created_at: datetime = Field(..., description="注册时间")

    model_config = {"from_attributes": True}
