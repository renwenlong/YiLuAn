from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
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


@router.get(
    "",
    response_model=list[CompanionListResponse],
    summary="搜索陪诊师列表",
    description="按区域、城市、服务类型、医院筛选可接单的陪诊师，分页返回。",
    responses={**err(401, 422, 500)},
)
async def list_companions(
    session: DBSession,
    current_user: CurrentUser,
    area: str | None = Query(None, description="服务区域关键字，如『朝阳区』"),
    city: str | None = Query(None, description="城市，如『北京』"),
    service_type: str | None = Query(None, description="服务类型：full_accompany / half_accompany / errand"),
    hospital_id: str | None = Query(None, description="按签约医院 ID 过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = CompanionProfileService(session)
    skip = (page - 1) * page_size
    return await service.list_companions(
        area=area, city=city, service_type=service_type, hospital_id=hospital_id, skip=skip, limit=page_size
    )


@router.get(
    "/me",
    response_model=CompanionDetailResponse,
    summary="获取我的陪诊师档案",
    description="返回当前登录用户的陪诊师档案；若用户未申请陪诊师角色将抛出 404。",
    responses={**err(401, 404, 500)},
)
async def get_my_profile(
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_detail_by_user(current_user.id, display_name=current_user.display_name)


@router.get(
    "/me/stats",
    response_model=CompanionStatsResponse,
    summary="获取陪诊师统计概览",
    description="返回当前陪诊师在接单量、完成量、平均评分、累计收入等维度的统计。",
    responses={**err(401, 403, 500)},
)
async def get_companion_stats(
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_stats(current_user)


@router.get(
    "/{companion_id}",
    response_model=CompanionDetailResponse,
    summary="查看陪诊师详情",
    description="根据陪诊师 ID 查看公开的资料、服务范围与评分概要。",
    responses={**err(401, 404, 500)},
)
async def get_companion(
    companion_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_detail(companion_id)


@router.post(
    "/apply",
    response_model=CompanionDetailResponse,
    status_code=201,
    summary="申请成为陪诊师",
    description=(
        "用户提交陪诊师入驻申请，填写真实姓名、服务区域、擅长项目等。"
        "提交后状态为 `pending`，需后台 `admin-companions` 模块审核。"
    ),
    responses={**err(400, 401, 422, 500)},
)
async def apply_companion(
    body: ApplyCompanionRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.apply(current_user, body)


@router.put(
    "/me",
    response_model=CompanionDetailResponse,
    summary="更新我的陪诊师档案",
    description="陪诊师本人更新服务区域、服务类型、签约医院、个人简介等可修改字段。",
    responses={**err(401, 403, 422, 500)},
)
async def update_companion_profile(
    body: UpdateCompanionProfileRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.update_profile(current_user.id, body, display_name=current_user.display_name)
