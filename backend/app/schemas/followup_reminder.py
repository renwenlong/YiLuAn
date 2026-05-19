"""F-07 schemas — 复诊提醒."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateFollowupReminderRequest(BaseModel):
    order_id: UUID = Field(..., description="订单 ID；必须是 completed / reviewed")
    remind_at: datetime = Field(..., description="提醒时间（UTC ISO 8601）")
    note: str | None = Field(None, max_length=140, description="自定义备注")


class FollowupReminderResponse(BaseModel):
    id: UUID
    user_id: UUID
    order_id: UUID
    remind_at: datetime
    status: str
    attempts: int
    note: str | None
    sent_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FollowupReminderListResponse(BaseModel):
    items: list[FollowupReminderResponse]
    total: int
