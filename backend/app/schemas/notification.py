from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: UUID = Field(..., description="通知 ID")
    user_id: UUID = Field(..., description="接收用户 ID")
    type: str = Field(..., description="通知类型", examples=["order_accepted"])
    title: str = Field(..., description="标题", examples=["陪诊师已接单"])
    body: str = Field(..., description="正文", examples=["您的订单已被陪诊师张三接单"])
    reference_id: str | None = Field(None, description="关联资源 ID（如 order_id）")
    is_read: bool = Field(..., description="是否已读")
    created_at: datetime = Field(..., description="发送时间")

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(..., description="当页通知")
    total: int = Field(..., description="总条数")


class UnreadCountResponse(BaseModel):
    count: int = Field(..., description="未读通知数", examples=[3])
