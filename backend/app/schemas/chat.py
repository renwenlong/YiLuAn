from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    # 与 WebSocket 聊天通道上限保持一致（D-019 Update 将 WS 聊天单条上限定为 4000 字符）
    content: str = Field(..., min_length=1, max_length=4000)
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
