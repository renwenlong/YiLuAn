"""Public service packages endpoint (S2-REQ-003-P3 / ADR-0043 §3).

公开访问，返回当前 active 服务档位列表，供 iOS/微信/admin 下单页获取价格。
按 sort_order 升序；is_active=False 不返回。
"""
from __future__ import annotations

from decimal import Decimal
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.service_package import ServicePackage

router = APIRouter(prefix="/public", tags=["public"])


class PublicServicePackage(BaseModel):
    code: str
    name: str
    price: Decimal
    sort_order: int
    description: str | None = None

    model_config = {"from_attributes": True}


@router.get(
    "/service-packages",
    response_model=List[PublicServicePackage],
    summary="获取服务档位列表 (公开)",
    description="返回当前 active 服务档位，按 sort_order 升序。以此价格为下单准，后台可动态调整。",
)
async def list_public_service_packages(
    db: AsyncSession = Depends(get_db),
) -> List[PublicServicePackage]:
    stmt = (
        select(ServicePackage)
        .where(ServicePackage.is_active.is_(True))
        .order_by(ServicePackage.sort_order.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PublicServicePackage.model_validate(r) for r in rows]
