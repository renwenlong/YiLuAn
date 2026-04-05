from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateOrderRequest(BaseModel):
    service_type: str = Field(..., pattern=r"^(full_accompany|half_accompany|errand)$")
    hospital_id: UUID
    appointment_date: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    appointment_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    description: str | None = None
    companion_id: UUID | None = None


class OrderResponse(BaseModel):
    id: UUID
    order_number: str
    patient_id: UUID
    companion_id: UUID | None = None
    hospital_id: UUID
    service_type: str
    status: str
    appointment_date: str
    appointment_time: str
    description: str | None = None
    price: float
    hospital_name: str | None = None
    companion_name: str | None = None
    patient_name: str | None = None
    payment_status: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OrderListResponse(BaseModel):
    items: list[OrderResponse]
    total: int


class PaymentResponse(BaseModel):
    id: UUID
    order_id: UUID
    user_id: UUID
    amount: float
    payment_type: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
