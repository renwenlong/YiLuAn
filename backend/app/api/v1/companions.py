from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import CurrentUser, DBSession
from app.schemas.companion import (
    ApplyCompanionRequest,
    CompanionDetailResponse,
    CompanionListResponse,
    CompanionStatsResponse,
    UpdateCompanionProfileRequest,
)
from app.services.companion_profile import CompanionProfileService

router = APIRouter(prefix="/companions", tags=["companions"])


@router.get("", response_model=list[CompanionListResponse], summary="获取陪诊师列表", description="分页查询陪诊师列表，支持按区域、城市、服务类型、医院筛选。")
async def list_companions(
    session: DBSession,
    current_user: CurrentUser,
    area: str | None = Query(None),
    city: str | None = Query(None),
    service_type: str | None = Query(None),
    hospital_id: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = CompanionProfileService(session)
    skip = (page - 1) * page_size
    return await service.list_companions(
        area=area, city=city, service_type=service_type, hospital_id=hospital_id, skip=skip, limit=page_size
    )


@router.get("/me", response_model=CompanionDetailResponse, summary="获取我的陪诊师档案", description="获取当前登录用户的陪诊师个人资料。")
async def get_my_profile(
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_detail_by_user(current_user.id, display_name=current_user.display_name)


@router.get("/me/stats", response_model=CompanionStatsResponse, summary="获取陪诊师统计数据", description="获取当前陪诊师的接单量、评分、收入等统计信息。")
async def get_companion_stats(
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_stats(current_user)


@router.get("/{companion_id}", response_model=CompanionDetailResponse, summary="获取陪诊师详情", description="根据陪诊师ID获取其详细资料和服务信息。")
async def get_companion(
    companion_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_detail(companion_id)


@router.post("/apply", response_model=CompanionDetailResponse, status_code=201, summary="申请成为陪诊师", description="用户提交陪诊师申请，填写服务区域、擅长科室等信息。")
async def apply_companion(
    body: ApplyCompanionRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.apply(current_user, body)


@router.put("/me", response_model=CompanionDetailResponse, summary="更新陪诊师档案", description="更新当前陪诊师的个人资料和服务信息。")
async def update_companion_profile(
    body: UpdateCompanionProfileRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.update_profile(current_user.id, body, display_name=current_user.display_name)
