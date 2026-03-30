from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)
    type: str = Field(default="text", pattern=r"^(text|image|system)$")


class ChatMessageResponse(BaseModel):
    id: UUID
    order_id: UUID
    sender_id: UUID
    type: str
    content: str
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse]
    total: int
