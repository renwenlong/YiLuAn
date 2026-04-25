import json
from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.api.v1.openapi_meta import err
from app.dependencies import DBSession
from app.schemas.hospital import (
    HospitalFiltersResponse,
    HospitalListResponse,
    HospitalRegionResponse,
    HospitalResponse,
)
from app.services.hospital import HospitalService

router = APIRouter(prefix="/hospitals", tags=["hospitals"])

CACHE_TTL = 3600  # 1 hour


def _cache_key(
    keyword: str | None,
    province: str | None,
    city: str | None,
    district: str | None,
    level: str | None,
    tag: str | None,
    page: int,
    page_size: int,
) -> str:
    return (
        f"hospitals:list:keyword={keyword or ''}:province={province or ''}"
        f":city={city or ''}:district={district or ''}:level={level or ''}"
        f":tag={tag or ''}:page={page}:page_size={page_size}"
    )


@router.get(
    "",
    response_model=HospitalListResponse,
    summary="分页搜索医院",
    description=(
        "按关键词 / 省市区 / 等级 / 标签搜索医院。结果带 1 小时 Redis 缓存，"
        "同一组查询参数命中缓存时直接返回。"
    ),
    responses={**err(422, 500)},
)
async def search_hospitals(
    request: Request,
    session: DBSession,
    keyword: str | None = Query(None, description="医院名称模糊匹配"),
    province: str | None = Query(None, description="省份名称"),
    city: str | None = Query(None, description="城市名称"),
    district: str | None = Query(None, description="区/县名称"),
    level: str | None = Query(None, description="医院等级，如『三甲』"),
    tag: str | None = Query(None, description="标签，如『综合』『儿科』"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    redis = request.app.state.redis
    cache_key = _cache_key(keyword, province, city, district, level, tag, page, page_size)

    cached = await redis.get(cache_key)
    if cached is not None:
        data = json.loads(cached)
        return HospitalListResponse(**data)

    service = HospitalService(session)
    skip = (page - 1) * page_size
    items, total = await service.search(
        keyword=keyword, province=province, city=city,
        district=district, level=level, tag=tag, skip=skip, limit=page_size,
    )
    response = HospitalListResponse(
        items=[HospitalResponse.model_validate(h) for h in items],
        total=total,
    )
    await redis.set(cache_key, response.model_dump_json(), ex=CACHE_TTL)
    return response


@router.get(
    "/filters",
    response_model=HospitalFiltersResponse,
    summary="获取医院筛选项",
    description="根据当前选择的省/市级联返回可用的下级筛选条件（省、市、区、等级、标签）。",
    responses={**err(500)},
)
async def get_hospital_filters(
    session: DBSession,
    province: str | None = Query(None, description="已选省份"),
    city: str | None = Query(None, description="已选城市"),
):
    service = HospitalService(session)
    options = await service.get_filter_options(province=province, city=city)
    return HospitalFiltersResponse(**options)


@router.get(
    "/nearest-region",
    response_model=HospitalRegionResponse,
    summary="按经纬度定位最近的省市",
    description="根据用户当前坐标，返回距离最近的医院所在的省、市，用于首屏自动选择城市。",
    responses={**err(422, 500)},
)
async def get_nearest_region(
    session: DBSession,
    latitude: float = Query(..., description="纬度", examples=[39.9087]),
    longitude: float = Query(..., description="经度", examples=[116.3975]),
):
    service = HospitalService(session)
    result = await service.find_nearest_region(latitude=latitude, longitude=longitude)
    if result is None:
        return HospitalRegionResponse(province=None, city=None)
    return HospitalRegionResponse(**result)


@router.get(
    "/{hospital_id}",
    response_model=HospitalResponse,
    summary="获取医院详情",
    description="根据医院 ID 返回完整字段（含坐标、等级、标签）。",
    responses={**err(404, 500)},
)
async def get_hospital(hospital_id: UUID, session: DBSession):
    service = HospitalService(session)
    return await service.get_by_id(hospital_id)


@router.post(
    "/seed",
    summary="导入种子医院数据（运维）",
    description=(
        "从内置数据文件批量导入医院信息到数据库。**仅在初始化部署或测试环境使用**，"
        "线上请通过运维流程而非公开调用。"
    ),
    responses={
        200: {
            "description": "导入完成",
            "content": {"application/json": {"example": {"seeded": 1024}}},
        },
        **err(500),
    },
)
async def seed_hospitals(session: DBSession):
    service = HospitalService(session)
    count = await service.seed_hospitals()
    return {"seeded": count}
