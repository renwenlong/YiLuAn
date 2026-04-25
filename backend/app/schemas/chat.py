from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    content: str = Field(
        ...,
        min_length=1,
        max_length=4000,
        description="消息正文，最长 4000 字符（与 WS 通道一致）",
        examples=["请问还要等多久？"],
    )
    type: str = Field(
        default="text",
        pattern=r"^(text|image|system)$",
        description="消息类型：text 文本 / image 图片 URL / system 系统消息",
        examples=["text"],
    )


class ChatMessageResponse(BaseModel):
    id: UUID = Field(..., description="消息 ID")
    order_id: UUID = Field(..., description="所属订单 ID")
    sender_id: UUID = Field(..., description="发送方用户 ID")
    type: str = Field(..., description="消息类型", examples=["text"])
    content: str = Field(..., description="消息正文", examples=["请问还要等多久？"])
    is_read: bool = Field(..., description="是否已读", examples=[False])
    created_at: datetime = Field(..., description="发送时间")

    model_config = {"from_attributes": True}


class ChatMessageListResponse(BaseModel):
    items: list[ChatMessageResponse] = Field(..., description="当页消息列表")
    total: int = Field(..., description="总条数", examples=[42])
