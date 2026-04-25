"""[F-03] Emergency call API.

- 紧急联系人 CRUD（最多 3 个）
- 触发紧急事件（呼叫联系人 / 客服热线）
- 列出历史紧急事件（个人）
"""
from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.openapi_meta import err
from app.config import settings
from app.dependencies import CurrentUser, DBSession
from app.schemas.emergency import (
    EmergencyContactCreate,
    EmergencyContactResponse,
    EmergencyContactUpdate,
    EmergencyEventResponse,
    EmergencyTriggerRequest,
    EmergencyTriggerResponse,
)
from app.services.emergency import EmergencyService

router = APIRouter(prefix="/emergency", tags=["emergency"])


@router.get(
    "/contacts",
    response_model=list[EmergencyContactResponse],
    summary="紧急联系人列表",
    responses={**err(401, 500)},
)
async def list_contacts(current_user: CurrentUser, session: DBSession):
    svc = EmergencyService(session)
    return await svc.list_contacts(current_user.id)


@router.post(
    "/contacts",
    response_model=EmergencyContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="新增紧急联系人（最多 3 个）",
    responses={**err(401, 409, 422, 500)},
)
async def create_contact(
    body: EmergencyContactCreate,
    current_user: CurrentUser,
    session: DBSession,
):
    svc = EmergencyService(session)
    return await svc.create_contact(current_user.id, body)


@router.put(
    "/contacts/{contact_id}",
    response_model=EmergencyContactResponse,
    summary="更新紧急联系人",
    responses={**err(401, 403, 404, 422, 500)},
)
async def update_contact(
    contact_id: UUID,
    body: EmergencyContactUpdate,
    current_user: CurrentUser,
    session: DBSession,
):
    svc = EmergencyService(session)
    return await svc.update_contact(current_user.id, contact_id, body)


@router.delete(
    "/contacts/{contact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="删除紧急联系人",
    responses={**err(401, 403, 404, 500)},
)
async def delete_contact(
    contact_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    svc = EmergencyService(session)
    await svc.delete_contact(current_user.id, contact_id)


@router.get(
    "/hotline",
    summary="平台客服热线",
    description="返回平台配置的客服热线，前端用于紧急呼叫弹层。",
)
async def get_hotline():
    return {"hotline": settings.emergency_hotline}


@router.post(
    "/events",
    response_model=EmergencyTriggerResponse,
    status_code=status.HTTP_201_CREATED,
    summary="触发紧急事件",
    description="患者点击紧急呼叫后调用：传入 contact_id 或 hotline=true，"
                "服务端记录审计并返回前端要 wx.makePhoneCall 的号码。",
    responses={**err(400, 401, 403, 404, 422, 500)},
)
async def trigger_event(
    body: EmergencyTriggerRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    svc = EmergencyService(session)
    event, phone = await svc.trigger_event(current_user.id, body)
    return EmergencyTriggerResponse(
        event=EmergencyEventResponse.model_validate(event),
        phone_to_call=phone,
    )


@router.get(
    "/events",
    response_model=list[EmergencyEventResponse],
    summary="我的紧急事件历史",
    responses={**err(401, 500)},
)
async def list_events(current_user: CurrentUser, session: DBSession):
    svc = EmergencyService(session)
    return await svc.event_repo.list_by_patient(current_user.id)
