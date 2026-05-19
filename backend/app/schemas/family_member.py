"""F-05: family-member schemas (代他人下单)."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.models.family_member import FamilyGender, FamilyRelation


_RELATION_VALUES = {r.value for r in FamilyRelation}
_GENDER_VALUES = {g.value for g in FamilyGender}


class CreateFamilyMemberRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=50, description="姓名")
    relation: str = Field(
        FamilyRelation.other.value,
        description="关系：parent/spouse/child/sibling/grandparent/relative/friend/other/self",
        examples=["parent"],
    )
    phone: str | None = Field(None, max_length=20, description="联系手机号（可空）")
    gender: str = Field(
        FamilyGender.unknown.value,
        description="性别：unknown/male/female",
        examples=["female"],
    )
    age: int | None = Field(None, ge=0, le=130, description="年龄")
    medical_notes: str | None = Field(None, description="就医备注 / 过敏史 / 慢病")

    @field_validator("relation")
    @classmethod
    def _v_relation(cls, v: str) -> str:
        if v not in _RELATION_VALUES:
            raise ValueError(f"Invalid relation: {v}")
        return v

    @field_validator("gender")
    @classmethod
    def _v_gender(cls, v: str) -> str:
        if v not in _GENDER_VALUES:
            raise ValueError(f"Invalid gender: {v}")
        return v

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v


class UpdateFamilyMemberRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=50)
    relation: str | None = Field(None)
    phone: str | None = Field(None, max_length=20)
    gender: str | None = Field(None)
    age: int | None = Field(None, ge=0, le=130)
    medical_notes: str | None = Field(None)

    @field_validator("relation")
    @classmethod
    def _v_relation(cls, v: str | None) -> str | None:
        if v is not None and v not in _RELATION_VALUES:
            raise ValueError(f"Invalid relation: {v}")
        return v

    @field_validator("gender")
    @classmethod
    def _v_gender(cls, v: str | None) -> str | None:
        if v is not None and v not in _GENDER_VALUES:
            raise ValueError(f"Invalid gender: {v}")
        return v

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return v  # caller may want to explicitly clear
        if not re.match(r"^1[3-9]\d{9}$", v):
            raise ValueError("Invalid phone number format")
        return v


class FamilyMemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    name: str
    relation: str
    phone: str | None
    gender: str
    age: int | None
    medical_notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FamilyMemberListResponse(BaseModel):
    items: list[FamilyMemberResponse]
    total: int


class OrderFamilyMemberSnapshot(BaseModel):
    """Denormalized snapshot embedded on Order responses so a deleted
    family member still appears correctly in historical orders."""

    id: UUID | None = Field(None, description="家人 ID（删除后仍保留快照）")
    name: str = Field(..., description="姓名")
    relation: str = Field(..., description="关系")
    phone: str | None = Field(None, description="联系电话")
