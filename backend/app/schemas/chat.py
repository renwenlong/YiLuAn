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
    has_more: bool = Field(
        default=False,
        description=(
            "上拉历史游标模式下：是否还有更早的消息。"
            "默认 page 分页模式总是 False。"
        ),
    )
    next_before_id: UUID | None = Field(
        default=None,
        description="下一页上拉历史应使用的游标；None 表示已无更多或不适用。",
    )


class ChatMessageBackfillResponse(BaseModel):
    """H3-be: WS 重连 / 增量回灌响应。

    严格按 ``(created_at ASC, id ASC)`` 返回。客户端可用 ``next_after_id``
    作为下一次回灌的游标，直到 ``has_more`` 为 ``False``。
    """

    items: list[ChatMessageResponse] = Field(
        ..., description="自游标之后的增量消息（升序）"
    )
    next_after_id: UUID | None = Field(
        default=None,
        description="下一次回灌应使用的游标 ID；为 None 表示已无更多",
    )
    has_more: bool = Field(
        default=False,
        description="是否仍有更多消息（即本批已被 limit 截断）",
    )
