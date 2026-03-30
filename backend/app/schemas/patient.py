import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, field_validator


class UpdatePatientProfileRequest(BaseModel):
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    medical_notes: str | None = None
    preferred_hospital_id: UUID | None = None

    @field_validator("emergency_phone")
    @classmethod
    def validate_phone(cls, v: str | None) -> str | None:
        if v is not None and v != "" and not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v


class PatientProfileResponse(BaseModel):
    id: UUID
    user_id: UUID
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    medical_notes: str | None = None
    preferred_hospital_id: UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
