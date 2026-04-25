"""[F-03] Emergency contact / event schemas."""
import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


class EmergencyContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="联系人姓名")
    phone: str = Field(..., description="联系人手机号")
    relationship: str = Field(..., min_length=1, max_length=20, description="与患者关系，如 配偶/子女/朋友")

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        if not _PHONE_RE.match(v):
            raise ValueError("Invalid phone number format")
        return v


class EmergencyContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    phone: str | None = None
    relationship: str | None = Field(None, min_length=1, max_length=20)

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not _PHONE_RE.match(v):
            raise ValueError("Invalid phone number format")
        return v


class EmergencyContactResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    phone: str
    relationship: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class EmergencyTriggerRequest(BaseModel):
    """触发紧急事件。

    - ``contact_id``: 选定的紧急联系人 ID（与 ``hotline`` 二选一）。
    - ``hotline``: 标记为呼叫平台客服热线，``contact_called`` 由后端从配置注入。
    - ``order_id``: 关联订单（服务进行中通常会有）。
    - ``location``: 可选的位置信息（自由格式字符串）。
    """

    order_id: UUID | None = None
    contact_id: UUID | None = None
    hotline: bool = False
    location: str | None = Field(None, max_length=255)


class EmergencyEventResponse(BaseModel):
    id: UUID
    patient_id: UUID
    order_id: UUID | None
    contact_called: str
    contact_type: str
    location: str | None
    triggered_at: datetime

    model_config = {"from_attributes": True}


class EmergencyTriggerResponse(BaseModel):
    event: EmergencyEventResponse
    phone_to_call: str = Field(..., description="前端应该 wx.makePhoneCall 拨打的号码")
