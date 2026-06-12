from uuid import UUID

from fastapi import APIRouter, Query

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession, WriteableUser
from app.schemas.companion import (
    ApplyCompanionRequest,
    CompanionDetailResponse,
    CompanionDirectoryDetailView,
    CompanionDirectoryView,
    CompanionStatsResponse,
    UpdateCompanionProfileRequest,
)
from app.schemas.recommendation import RecommendationResponse
from app.services.companion_profile import (
    CompanionProfileService,
    _to_public_detail_view,
    _to_public_view,
)
from app.services.recommendation_service import RecommendationService

router = APIRouter(prefix="/companions", tags=["companions"])


@router.get(
    "",
    response_model=list[CompanionDirectoryView],
    summary="搜索陪诊师列表",
    description=(
        "按区域、城市、服务类型、医院筛选可接单的陪诊师，分页返回。"
        "\n\n**ABAC**: 返回 ``CompanionDirectoryView`` (no PII), "
        "使用 ``mask_name`` 脱敏 生成 ``pseudonym_name``。"
        "严禁返 ``real_name`` / ``id_number`` / "
        "``certification_no`` / ``certification_image_url``。"
    ),
    responses={**err(401, 422, 500)},
)
async def list_companions(
    session: DBSession,
    current_user: CurrentUser,
    area: str | None = Query(None, description="服务区域关键字，如『朝阳区』"),
    city: str | None = Query(None, description="城市，如『北京』"),
    service_type: str | None = Query(
        None, description="服务类型：full_accompany / half_accompany / errand"
    ),
    hospital_id: str | None = Query(None, description="按签约医院 ID 过滤"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = CompanionProfileService(session)
    skip = (page - 1) * page_size
    profiles = await service.list_companions(
        area=area,
        city=city,
        service_type=service_type,
        hospital_id=hospital_id,
        skip=skip,
        limit=page_size,
    )
    # ABAC layer 2: service-layer masking before response_model serialization
    return [_to_public_view(p) for p in profiles]


@router.get(
    "/recommendations",
    response_model=RecommendationResponse,
    summary="陕诊师推荐位 top3",
    description=(
        "返回 top3 推荐陕诊师 (默认 N=3, 可通过 top_k 参数调)。\n\n"
        "**排序规则** (spec v1 final §1.3): verified > pending_supplement > uncertified, "
        "同 level tie-breaker rating DESC → completed_orders DESC → created_at ASC.\n\n"
        "**硕约束门** (spec §1.4, PM-005-9 admin override 守门): 未认证 (uncertified) "
        "陕诊师不进 top3, admin 不可 override (服务层硬编码 filter, 不依赖 admin endpoint).\n\n"
        "**ABAC** (ADR-0049 §6): 返 ``RecommendationItem`` (no PII), "
        "使用 ``mask_name`` 脚敏生成 ``pseudonym_name``。严禁返 ``real_name`` / "
        "``id_number`` / ``certification_no`` / ``certification_image_url``。"
    ),
    responses={**err(401, 422, 500)},
)
async def get_recommendations(
    session: DBSession,
    current_user: CurrentUser,
    city: str | None = Query(None, description="可选城市过滤 (spec §1.5)"),
    top_k: int = Query(3, ge=1, le=3, description="推荐位 N (default=3, max=3)"),
):
    service = RecommendationService(session)
    return await service.get_top_recommendations(city=city, top_k=top_k)


@router.get(
    "/me",
    response_model=CompanionDetailResponse,
    summary="获取我的陪诊师档案",
    description=(
        "返回当前登录用户的陪诊师档案；若用户未申请陪诊师角色将抛出 404。"
        "\n\n**ABAC**: 用户看自己, OK 返 real_name (本身)。"
    ),
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
    response_model=CompanionDirectoryDetailView,
    summary="查看陪诊师详情",
    description=(
        "根据陪诊师 ID 查看公开的资料、服务范围与评分概要。"
        "\n\n**ABAC**: 返 ``CompanionDirectoryDetailView`` (no PII)。"
        "严禁 ``real_name`` / ``certification_no`` / "
        "``certification_image_url``。"
    ),
    responses={**err(401, 404, 500)},
)
async def get_companion(
    companion_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    profile = await service.get_detail(companion_id)
    # ABAC layer 2: service-layer masking before response_model serialization
    return _to_public_detail_view(profile)


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
    current_user: WriteableUser,
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
    current_user: WriteableUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.update_profile(
        current_user.id, body, display_name=current_user.display_name
    )
