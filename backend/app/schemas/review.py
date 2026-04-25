from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class CreateReviewRequest(BaseModel):
    """提交评价（F-04 多维度评分）。

    支持两种模式以保证向后兼容：

    1. **旧模式**：仅传 `rating`（1~5），4 个维度自动填同值。
    2. **新模式**：传 4 个维度评分，`rating` 自动 = 加权平均（默认等权 0.25）。
       兼容传入 `rating` 时以 4 维度加权平均为准（覆盖客户端传值）。
    """

    rating: int | None = Field(
        None, ge=1, le=5, description="总评分 1~5 星（兼容字段；若传 4 维度则忽略）", examples=[5]
    )
    punctuality_rating: int | None = Field(
        None, ge=1, le=5, description="守时维度评分 1~5", examples=[5]
    )
    professionalism_rating: int | None = Field(
        None, ge=1, le=5, description="专业维度评分 1~5", examples=[5]
    )
    communication_rating: int | None = Field(
        None, ge=1, le=5, description="沟通维度评分 1~5", examples=[5]
    )
    attitude_rating: int | None = Field(
        None, ge=1, le=5, description="态度维度评分 1~5", examples=[5]
    )
    content: str = Field(
        ..., min_length=5, max_length=500, description="文字评价 5~500 字",
        examples=["陪诊师非常专业，全程耐心解答。"],
    )

    @model_validator(mode="after")
    def _require_rating_or_dimensions(self) -> "CreateReviewRequest":
        dims = [
            self.punctuality_rating,
            self.professionalism_rating,
            self.communication_rating,
            self.attitude_rating,
        ]
        any_dim = any(d is not None for d in dims)
        all_dim = all(d is not None for d in dims)
        if any_dim and not all_dim:
            raise ValueError("4 个维度评分必须同时提供")
        if not any_dim and self.rating is None:
            raise ValueError("必须提供 rating 或 4 个维度评分")
        return self


class ReviewResponse(BaseModel):
    id: UUID = Field(..., description="评价 ID")
    order_id: UUID = Field(..., description="订单 ID")
    patient_id: UUID = Field(..., description="患者 ID")
    companion_id: UUID = Field(..., description="陪诊师 ID")
    rating: int = Field(..., description="总评分（4 维度加权平均，四舍五入到整数）", examples=[5])
    punctuality_rating: int | None = Field(None, description="守时维度评分", examples=[5])
    professionalism_rating: int | None = Field(None, description="专业维度评分", examples=[5])
    communication_rating: int | None = Field(None, description="沟通维度评分", examples=[5])
    attitude_rating: int | None = Field(None, description="态度维度评分", examples=[5])
    content: str | None = Field(None, description="评论")
    patient_name: str | None = Field(None, description="患者昵称（脱敏可选）")
    created_at: datetime = Field(..., description="评价时间")

    model_config = {"from_attributes": True}


class ReviewListResponse(BaseModel):
    items: list[ReviewResponse] = Field(..., description="当页评价列表")
    total: int = Field(..., description="总条数")
