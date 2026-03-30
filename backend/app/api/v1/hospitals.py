from uuid import UUID

from fastapi import APIRouter, Query

from app.dependencies import DBSession
from app.schemas.hospital import HospitalListResponse, HospitalResponse
from app.services.hospital import HospitalService

router = APIRouter(prefix="/hospitals", tags=["hospitals"])


@router.get("", response_model=HospitalListResponse)
async def search_hospitals(
    session: DBSession,
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    service = HospitalService(session)
    skip = (page - 1) * page_size
    items, total = await service.search(keyword=keyword, skip=skip, limit=page_size)
    return HospitalListResponse(
        items=[HospitalResponse.model_validate(h) for h in items],
        total=total,
    )


@router.get("/{hospital_id}", response_model=HospitalResponse)
async def get_hospital(hospital_id: UUID, session: DBSession):
    service = HospitalService(session)
    return await service.get_by_id(hospital_id)


@router.post("/seed")
async def seed_hospitals(session: DBSession):
    service = HospitalService(session)
    count = await service.seed_hospitals()
    return {"seeded": count}
