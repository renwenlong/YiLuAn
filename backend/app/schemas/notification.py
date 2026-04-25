from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    id: UUID = Field(..., description="通知 ID")
    user_id: UUID = Field(..., description="用户 ID")
    type: str = Field(..., description="通知类型", examples=["order_status_changed"])
    title: str = Field(..., description="标题", examples=["订单状态更新"])
    body: str = Field(..., description="正文", examples=["您的订单已被接单"])
    reference_id: str | None = Field(None, description="关联实体 ID（兼容字段）")
    target_type: str | None = Field(
        None,
        description="[F-02] 深链跳转目标类型: order/companion/system/payment/review",
        examples=["order"],
    )
    target_id: str | None = Field(
        None, description="[F-02] 深链跳转目标 ID", examples=["6f1d…"]
    )
    is_read: bool = Field(..., description="是否已读")
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}


class NotificationListResponse(BaseModel):
    items: list[NotificationResponse] = Field(..., description="通知列表")
    total: int = Field(..., description="总数")


class UnreadCountResponse(BaseModel):
    count: int = Field(..., description="未读数量", examples=[3])


class MarkReadResponse(BaseModel):
    """[F-02] 标已读后返回当前 target 信息，便于前端立刻跳转。"""

    success: bool = Field(..., description="是否成功标记为已读")
    notification: NotificationResponse | None = Field(
        None,
        description="若通知存在则返回最新内容（含 target_type / target_id），否则为 null",
    )
