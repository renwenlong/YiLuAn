from fastapi import APIRouter

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.schemas.patient import PatientProfileResponse, UpdatePatientProfileRequest
from app.services.patient_profile import PatientProfileService

router = APIRouter(prefix="/users", tags=["patients"])


@router.get(
    "/me/patient-profile",
    response_model=PatientProfileResponse,
    summary="获取我的患者档案",
    description="获取当前登录用户的患者档案；不存在则自动创建一条空档案后返回。",
    responses={**err(401, 500)},
)
async def get_patient_profile(current_user: CurrentUser, session: DBSession):
    service = PatientProfileService(session)
    return await service.get_or_create(current_user.id)


@router.put(
    "/me/patient-profile",
    response_model=PatientProfileResponse,
    summary="更新我的患者档案",
    description="更新当前用户的患者档案：紧急联系人、紧急联系人手机号、就医备注、常用医院。",
    responses={**err(401, 422, 500)},
)
async def update_patient_profile(
    body: UpdatePatientProfileRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    service = PatientProfileService(session)
    return await service.update_profile(current_user.id, body)
