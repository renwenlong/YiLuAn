from fastapi import APIRouter

from app.dependencies import CurrentUser, DBSession
from app.schemas.patient import PatientProfileResponse, UpdatePatientProfileRequest
from app.services.patient_profile import PatientProfileService

router = APIRouter(prefix="/users", tags=["patients"])


@router.get("/me/patient-profile", response_model=PatientProfileResponse, summary="获取患者档案", description="获取当前用户的患者档案信息，不存在则自动创建。")
async def get_patient_profile(current_user: CurrentUser, session: DBSession):
    service = PatientProfileService(session)
    return await service.get_or_create(current_user.id)


@router.put("/me/patient-profile", response_model=PatientProfileResponse, summary="更新患者档案", description="更新当前用户的患者档案信息，如就诊需求、健康状况等。")
async def update_patient_profile(
    body: UpdatePatientProfileRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = PatientProfileService(session)
    return await service.update_profile(current_user.id, body)
