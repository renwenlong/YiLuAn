from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateReviewRequest(BaseModel):
    rating: int = Field(..., ge=1, le=5, description="评分 1~5 星", examples=[5])
    content: str = Field(..., min_length=5, max_length=500, description="文字评价 5~500 字", examples=["陪诊师非常专业，全程耐心解答。"])


class ReviewResponse(BaseModel):
    id: UUID = Field(..., description="评价 ID")
    order_id: UUID = Field(..., description="订单 ID")
    patient_id: UUID = Field(..., description="患者 ID")
    companion_id: UUID = Field(..., description="陪诊师 ID")
    rating: int = Field(..., description="评分", examples=[5])
    content: str | None = Field(None, description="评论")
    patient_name: str | None = Field(None, description="患者昵称（脱敏可选）")
    created_at: datetime = Field(..., description="评价时间")

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse] = Field(..., description="当页评价列表")
    total: int = Field(..., description="总条数")
