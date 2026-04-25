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
    description="返回当前用户配置的紧急联系人（最多 3 个），按 created_at 升序。",
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
    description="为当前用户新增一位紧急联系人；超过 3 个或重复手机号会返回 409。",
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
    description="更新指定 contact_id 的姓名 / 关系 / 手机号；非本人持有返回 403。",
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
    description="软删除指定的紧急联系人；非本人持有返回 403。",
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
    description="返回当前用户触发过的紧急事件列表，按 created_at 降序，用于历史回溯审计。",
    responses={**err(401, 500)},
)
async def list_events(current_user: CurrentUser, session: DBSession):
    svc = EmergencyService(session)
    return await svc.event_repo.list_by_patient(current_user.id)
