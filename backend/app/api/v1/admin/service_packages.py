"""Admin service_packages CRUD endpoints (S2-REQ-003 P2 / ADR-0043 §2.4 + §3 Phase 2).

5 endpoints:
- GET    /admin/service-packages/
        列表（默认仅 active；?include_inactive=true 拉全）
- GET    /admin/service-packages/{id}
        单条详情
- POST   /admin/service-packages/
        创建（code 唯一 + price > 0 + sort_order >= 0）
- PATCH  /admin/service-packages/{id}
        部分更新（name/price/is_active/sort_order/description）
- DELETE /admin/service-packages/{id}
        软删（is_active=false，不真删，避免历史 Order 引用断裂）

所有 mutation 写 admin_audit_logs，reason 字段塞 JSON 串携带 before/after diff
（刻晴 P2 review 建议）。
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.core.admin_jwt import admin_operator_id, require_admin
from app.dependencies import DBSession
from app.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models.admin_audit_log import AdminAuditLog
from app.models.service_package import ServicePackage

router = APIRouter(
    prefix="/service-packages",
    tags=["admin-service-packages"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ServicePackageItem(BaseModel):
    """对外暴露的 ServicePackage 字段（与 ORM 1:1）。"""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="主键 UUID 字符串")
    code: str = Field(..., description="业务编码（unique，Order.service_type 引用此字段）")
    name: str = Field(..., description="中文显示名")
    price: Decimal = Field(..., description="价格（元，Decimal 遵 ADR-0030）")
    is_active: bool = Field(..., description="启用状态")
    sort_order: int = Field(..., description="排序权重（升序）")
    description: str | None = Field(None, description="详情说明（可选）")
    created_at: str | None = Field(None, description="创建时间 ISO8601")
    updated_at: str | None = Field(None, description="更新时间 ISO8601")


class ServicePackageListResponse(BaseModel):
    items: list[ServicePackageItem] = Field(default_factory=list)
    total: int = Field(0, description="总条数")


class ServicePackageCreateBody(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="业务编码，unique")
    name: str = Field(..., min_length=1, max_length=100, description="中文显示名")
    price: Decimal = Field(..., gt=Decimal("0"), description="价格（必须 > 0）")
    sort_order: int = Field(0, ge=0, description="排序权重")
    description: str | None = Field(None, max_length=500, description="详情说明（可选）")
    is_active: bool = Field(True, description="是否启用，默认 true")


class ServicePackageUpdateBody(BaseModel):
    """部分更新；未传字段不动。"""

    name: str | None = Field(None, min_length=1, max_length=100)
    price: Decimal | None = Field(None, gt=Decimal("0"))
    sort_order: int | None = Field(None, ge=0)
    description: str | None = Field(None, max_length=500)
    is_active: bool | None = Field(None)


class OkResponse(BaseModel):
    ok: bool = Field(True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_item(pkg: ServicePackage) -> dict:
    return {
        "id": str(pkg.id),
        "code": pkg.code,
        "name": pkg.name,
        "price": pkg.price,
        "is_active": pkg.is_active,
        "sort_order": pkg.sort_order,
        "description": pkg.description,
        "created_at": pkg.created_at.isoformat() if pkg.created_at else None,
        "updated_at": pkg.updated_at.isoformat() if pkg.updated_at else None,
    }


def _snapshot(pkg: ServicePackage) -> dict:
    """快照仅保存关键 mutable 字段，用于 audit diff。"""
    return {
        "code": pkg.code,
        "name": pkg.name,
        "price": str(pkg.price),
        "is_active": pkg.is_active,
        "sort_order": pkg.sort_order,
        "description": pkg.description,
    }


def _audit_reason(action: str, before: dict | None, after: dict | None) -> str:
    """audit_log.reason = JSON 串 {action, before, after}.

    AdminAuditLog 没有 payload column；复用 reason (Text) 携带 diff 元数据。
    刻晴 review 关切：mutation 必须可回溯 before/after。
    """
    payload = {"action": action, "before": before, "after": after}
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


async def _get_pkg_or_404(session, pkg_id: UUID) -> ServicePackage:
    pkg = await session.get(ServicePackage, pkg_id)
    if pkg is None:
        raise NotFoundException("service_package_not_found")
    return pkg


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/",
    response_model=ServicePackageListResponse,
    summary="后台：服务档位列表",
    description=(
        "默认仅返回 is_active=true。?include_inactive=true 拉全部（含软删）。"
        "按 sort_order 升序。"
    ),
)
async def list_service_packages(
    session: DBSession,
    operator: str = Depends(admin_operator_id),  # noqa: ARG001 (auth required)
    include_inactive: bool = Query(
        False, description="为 true 时返回 is_active=false 的软删项"
    ),
):
    stmt = select(ServicePackage)
    if not include_inactive:
        stmt = stmt.where(ServicePackage.is_active.is_(True))
    stmt = stmt.order_by(ServicePackage.sort_order.asc(), ServicePackage.code.asc())
    result = await session.execute(stmt)
    pkgs = result.scalars().all()
    items = [_to_item(p) for p in pkgs]
    return {"items": items, "total": len(items)}


@router.get(
    "/{pkg_id}",
    response_model=ServicePackageItem,
    summary="后台：服务档位详情",
)
async def get_service_package(
    pkg_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),  # noqa: ARG001
):
    pkg = await _get_pkg_or_404(session, pkg_id)
    return _to_item(pkg)


@router.post(
    "/",
    response_model=ServicePackageItem,
    status_code=201,
    summary="后台：新建服务档位",
    description="code 全局唯一；price 必须 > 0；写 admin_audit_log create + before/after diff。",
)
async def create_service_package(
    body: ServicePackageCreateBody,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    # 唯一性预检（DB unique 也会兜底，但前置 409 比 500 友好）
    existing = await session.execute(
        select(ServicePackage).where(ServicePackage.code == body.code)
    )
    if existing.scalar_one_or_none() is not None:
        raise ConflictException("service_package_code_exists")

    pkg = ServicePackage(
        code=body.code,
        name=body.name,
        price=body.price,
        sort_order=body.sort_order,
        description=body.description,
        is_active=body.is_active,
    )
    session.add(pkg)
    await session.flush()

    after = _snapshot(pkg)
    session.add(
        AdminAuditLog(
            target_type="service_package",
            target_id=pkg.id,
            action="service_package_create",
            operator=operator,
            reason=_audit_reason("create", before=None, after=after),
        )
    )
    await session.flush()
    await session.refresh(pkg)
    return _to_item(pkg)


@router.patch(
    "/{pkg_id}",
    response_model=ServicePackageItem,
    summary="后台：更新服务档位",
    description=(
        "部分更新 name/price/is_active/sort_order/description；code 不可改"
        "（避免历史 Order.service_type 引用断裂）。写 admin_audit_log update + before/after diff。"
    ),
)
async def update_service_package(
    pkg_id: UUID,
    body: ServicePackageUpdateBody,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    pkg = await _get_pkg_or_404(session, pkg_id)
    before = _snapshot(pkg)

    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise BadRequestException("service_package_update_empty")

    for k, v in update_data.items():
        # price 走 Decimal 强转防止前端串了 string
        if k == "price" and v is not None and not isinstance(v, Decimal):
            try:
                v = Decimal(str(v))
            except (InvalidOperation, ValueError) as exc:
                raise BadRequestException("service_package_price_invalid") from exc
        setattr(pkg, k, v)

    await session.flush()
    await session.refresh(pkg)
    after = _snapshot(pkg)

    session.add(
        AdminAuditLog(
            target_type="service_package",
            target_id=pkg.id,
            action="service_package_update",
            operator=operator,
            reason=_audit_reason("update", before=before, after=after),
        )
    )
    await session.flush()
    return _to_item(pkg)


@router.delete(
    "/{pkg_id}",
    response_model=OkResponse,
    summary="后台：软删服务档位",
    description=(
        "软删（is_active=false）。**不真删**，避免历史 Order.service_type 引用断裂"
        "（ADR-0043 §2.2 弱外键策略）。写 admin_audit_log soft_delete。"
    ),
)
async def soft_delete_service_package(
    pkg_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    pkg = await _get_pkg_or_404(session, pkg_id)
    if not pkg.is_active:
        # 已软删幂等：仍写 audit 留痕，但不真改字段
        before = _snapshot(pkg)
        session.add(
            AdminAuditLog(
                target_type="service_package",
                target_id=pkg.id,
                action="service_package_soft_delete",
                operator=operator,
                reason=_audit_reason(
                    "soft_delete_noop_already_inactive",
                    before=before,
                    after=before,
                ),
            )
        )
        await session.flush()
        return {"ok": True}

    before = _snapshot(pkg)
    pkg.is_active = False
    await session.flush()
    await session.refresh(pkg)
    after = _snapshot(pkg)

    session.add(
        AdminAuditLog(
            target_type="service_package",
            target_id=pkg.id,
            action="service_package_soft_delete",
            operator=operator,
            reason=_audit_reason("soft_delete", before=before, after=after),
        )
    )
    await session.flush()
    return {"ok": True}
