import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class UpdatePatientProfileRequest(BaseModel):
    emergency_contact: str | None = Field(None, description="紧急联系人姓名", examples=["王芳"])
    emergency_phone: str | None = Field(None, description="紧急联系人手机号", examples=["13900139000"])
    medical_notes: str | None = Field(None, description="就医备注（过敏史、慢病等）", examples=["青霉素过敏"])
    preferred_hospital_id: UUID | None = Field(None, description="常用医院 ID")

    @field_validator("emergency_phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v


class PatientProfileResponse(BaseModel):
    id: UUID = Field(..., description="档案 ID")
    user_id: UUID = Field(..., description="用户 ID")
    emergency_contact: str | None = Field(None, description="紧急联系人")
    emergency_phone: str | None = Field(None, description="紧急联系电话")
    medical_notes: str | None = Field(None, description="就医备注")
    preferred_hospital_id: UUID | None = Field(None, description="常用医院 ID")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    model_config = {"from_attributes": True}
