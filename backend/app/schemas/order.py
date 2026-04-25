from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    service_type: str = Field(
        ...,
        pattern=r"^(full_accompany|half_accompany|errand)$",
        description="服务类型：full_accompany 全程陪诊 / half_accompany 半天陪诊 / errand 跑腿代办",
        examples=["full_accompany"],
    )
    hospital_id: UUID = Field(..., description="目标医院 ID")
    appointment_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$", description="预约日期", examples=["2026-05-01"])
    appointment_time: str = Field(..., pattern=r"^\d{2}:\d{2}$", description="预约时间 HH:MM", examples=["09:30"])
    description: str | None = Field(None, description="补充说明（病情、特殊需求）", examples=["需要陪同做核磁，行动不便"])
    companion_id: UUID | None = Field(None, description="可选：直接指派的陪诊师 ID；为空则进入大厅抢单")


class TimelineItem(BaseModel):
    title: str = Field(..., description="阶段名称", examples=["已接单"])
    time: str = Field(..., description="发生时间 ISO8601", examples=["2026-04-24T10:05:00+08:00"])


class OrderResponse(BaseModel):
    id: UUID = Field(..., description="订单 ID")
    order_number: str = Field(..., description="订单号（业务可见）", examples=["YLA20260424100501"])
    patient_id: UUID = Field(..., description="患者用户 ID")
    companion_id: UUID | None = Field(None, description="陪诊师用户 ID（未接单时为空）")
    hospital_id: UUID = Field(..., description="医院 ID")
    service_type: str = Field(..., description="服务类型", examples=["full_accompany"])
    status: str = Field(..., description="订单状态", examples=["paid"])
    appointment_date: str = Field(..., description="预约日期", examples=["2026-05-01"])
    appointment_time: str = Field(..., description="预约时间", examples=["09:30"])
    description: str | None = Field(None, description="患者补充说明")
    price: float = Field(..., description="订单金额（元）", examples=[199.00])
    hospital_name: str | None = Field(None, description="医院名称（冗余）", examples=["北京协和医院"])
    companion_name: str | None = Field(None, description="陪诊师姓名（冗余）", examples=["张三"])
    patient_name: str | None = Field(None, description="患者姓名（冗余）", examples=["小明"])
    payment_status: str | None = Field(None, description="支付状态", examples=["success"])
    expires_at: datetime | None = Field(None, description="待支付订单的过期时间")
    timeline: list[TimelineItem] | None = Field(None, description="订单时间轴")
    timeline_index: int | None = Field(None, description="当前时间轴索引")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse] = Field(..., description="当页订单")
    total: int = Field(..., description="总条数")


class PaymentResponse(BaseModel):
    id: UUID = Field(..., description="支付/退款记录 ID")
    order_id: UUID = Field(..., description="所属订单 ID")
    user_id: UUID = Field(..., description="发起用户 ID")
    amount: float = Field(..., description="金额（元）", examples=[199.00])
    payment_type: str = Field(..., description="类型：pay / refund", examples=["pay"])
    status: str = Field(..., description="状态：pending / success / failed", examples=["success"])
    created_at: datetime = Field(..., description="创建时间")

    model_config = {"from_attributes": True}
