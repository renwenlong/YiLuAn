"""F-07 routes: 复诊提醒 CRUD.

* 创建：必须 order.status ∈ {completed, reviewed} 且 order.patient_id == 当前用户
* 列表：当前用户自己的提醒（按 remind_at asc）
* 删除：仅 pending 可取消（已 sent 不能撤回）
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentUser, DBSession
from app.exceptions import BadRequestException, NotFoundException
from app.models.followup_reminder import FollowupReminder, FollowupReminderStatus
from app.models.order import OrderStatus
from app.repositories.followup_reminder import FollowupReminderRepository
from app.repositories.order import OrderRepository
from app.schemas.followup_reminder import (
    CreateFollowupReminderRequest,
    FollowupReminderListResponse,
    FollowupReminderResponse,
)

router = APIRouter(prefix="/orders", tags=["followup-reminders"])

_ALLOWED_ORDER_STATUSES = {OrderStatus.completed, OrderStatus.reviewed}


@router.post(
    "/{order_id}/followup-reminders",
    response_model=FollowupReminderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="为一笔已完成订单创建复诊提醒 (F-07)",
    responses={**err(400, 401, 404, 422, 500)},
)
async def create_followup_reminder(
    order_id: UUID,
    body: CreateFollowupReminderRequest,
    current_user: CurrentUser,
    session: DBSession,
):
    # path 与 body order_id 必须一致（防止前端 bug）
    if body.order_id != order_id:
        raise BadRequestException("order_id mismatch between path and body")

    order_repo = OrderRepository(session)
    order = await order_repo.get_by_id(order_id)
    if order is None or order.patient_id != current_user.id:
        raise NotFoundException("Order not found")
    if order.status not in _ALLOWED_ORDER_STATUSES:
        raise BadRequestException(
            "Followup reminder is only allowed after order completion"
        )

    repo = FollowupReminderRepository(session)
    reminder = FollowupReminder(
        user_id=current_user.id,
        order_id=order_id,
        remind_at=body.remind_at,
        note=body.note,
    )
    reminder = await repo.create(reminder)
    return FollowupReminderResponse.model_validate(reminder)


@router.get(
    "/me/followup-reminders",
    response_model=FollowupReminderListResponse,
    summary="我的全部复诊提醒 (F-07)",
    responses={**err(401, 500)},
)
async def list_my_followup_reminders(
    current_user: CurrentUser, session: DBSession
):
    repo = FollowupReminderRepository(session)
    items = await repo.list_by_user(current_user.id)
    return FollowupReminderListResponse(
        items=[FollowupReminderResponse.model_validate(r) for r in items],
        total=len(items),
    )


@router.delete(
    "/me/followup-reminders/{reminder_id}",
    status_code=204,
    summary="取消一条 pending 复诊提醒 (F-07)",
    responses={**err(400, 401, 404, 500)},
)
async def cancel_followup_reminder(
    reminder_id: UUID,
    current_user: CurrentUser,
    session: DBSession,
):
    repo = FollowupReminderRepository(session)
    reminder = await repo.get_for_user(reminder_id, current_user.id)
    if reminder is None:
        raise NotFoundException("Reminder not found")
    if reminder.status != FollowupReminderStatus.pending:
        raise BadRequestException(
            "Only pending reminders can be cancelled"
        )
    await repo.update(reminder, {"status": FollowupReminderStatus.cancelled})
    return None
