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


@router.get("", response_model=list[CompanionListResponse])
async def list_companions(
    session: DBSession,
    current_user: CurrentUser,
    area: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = CompanionProfileService(session)
    skip = (page - 1) * page_size
    return await service.list_companions(area=area, skip=skip, limit=page_size)


@router.get("/me/stats", response_model=CompanionStatsResponse)
async def get_companion_stats(
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_stats(current_user)


@router.get("/{companion_id}", response_model=CompanionDetailResponse)
async def get_companion(
    companion_id: UUID,
    session: DBSession,
    current_user: CurrentUser,
):
    service = CompanionProfileService(session)
    return await service.get_detail(companion_id)


@router.post("/apply", response_model=CompanionDetailResponse, status_code=201)
async def apply_companion(
    body: ApplyCompanionRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.apply(current_user, body)


@router.put("/me", response_model=CompanionDetailResponse)
async def update_companion_profile(
    body: UpdateCompanionProfileRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = CompanionProfileService(session)
    return await service.update_profile(current_user.id, body)
