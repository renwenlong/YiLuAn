from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApplyCompanionRequest(BaseModel):
    real_name: str = Field(..., min_length=2, max_length=50, description="真实姓名", examples=["张三"])
    id_number: str | None = Field(None, description="身份证号", examples=["110101199001011234"])
    certifications: str | None = Field(None, description="资质证书描述（多个用逗号分隔）", examples=["护士资格证,养老护理员"])
    service_area: str | None = Field(None, description="服务区域，如『朝阳区,海淀区』", examples=["朝阳区,海淀区"])
    service_types: str = Field(..., min_length=1, max_length=200, description="提供的服务类型，逗号分隔", examples=["full_accompany,half_accompany"])
    service_hospitals: str | None = Field(None, description="签约医院 ID 列表，逗号分隔")
    service_city: str | None = Field(None, description="服务城市", examples=["北京"])
    bio: str | None = Field(None, description="个人简介", examples=["5 年三甲医院护理经验"])


class UpdateCompanionProfileRequest(BaseModel):
    service_area: str | None = Field(None, description="服务区域")
    service_types: str | None = Field(None, description="服务类型")
    bio: str | None = Field(None, description="个人简介")
    certifications: str | None = Field(None, description="资质证书")
    service_hospitals: str | None = Field(None, description="签约医院")
    service_city: str | None = Field(None, description="服务城市")


class CompanionListResponse(BaseModel):
    id: UUID = Field(..., description="陪诊师档案 ID")
    user_id: UUID = Field(..., description="对应用户 ID")
    real_name: str = Field(..., description="真实姓名")
    service_area: str | None = Field(None, description="服务区域")
    service_types: str | None = Field(None, description="服务类型")
    service_hospitals: str | None = Field(None, description="签约医院 ID 列表")
    service_city: str | None = Field(None, description="服务城市")
    bio: str | None = Field(None, description="个人简介")
    avg_rating: float = Field(0.0, description="平均评分（0~5）", examples=[4.8])
    total_orders: int = Field(0, description="累计完成订单数", examples=[126])
    verification_status: str = Field("pending", description="审核状态：pending/verified/rejected", examples=["verified"])

    model_config = {"from_attributes": True}


class CompanionDetailResponse(CompanionListResponse):
    certifications: str | None = Field(None, description="资质证书")
    certification_type: str | None = Field(None, description="认证类型（护士证 / 健康管理师等）", examples=["护士证"])
    certification_no: str | None = Field(None, description="证书编号", examples=["NO.20231234"])
    certification_image_url: str | None = Field(None, description="证书图片 OSS URL")
    certified_at: datetime | None = Field(None, description="认证通过时间")
    created_at: datetime = Field(..., description="档案创建时间")

    model_config = {"from_attributes": True}


class CertifyCompanionRequest(BaseModel):
    """管理员为陪诊师设置资质认证（F-01）。"""

    certification_type: str = Field(..., min_length=1, max_length=50, description="认证类型（护士证 / 健康管理师等）", examples=["护士证"])
    certification_no: str = Field(..., min_length=1, max_length=100, description="证书编号", examples=["NO.20231234"])
    certification_image_url: str = Field(..., min_length=1, max_length=500, description="证书图片 OSS URL")


class CompanionStatsResponse(BaseModel):
    open_orders: int = Field(0, description="进行中订单数", examples=[2])
    total_orders: int = Field(0, description="累计订单数", examples=[126])
    avg_rating: float = Field(0.0, description="平均评分", examples=[4.8])
    total_earnings: float = Field(0.0, description="累计收入（元）", examples=[12480.50])
