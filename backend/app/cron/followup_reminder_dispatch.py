"""F-07 cron: dispatch pending follow-up reminders.

每分钟执行一次（k8s CronJob 或 OpenClaw cron 调度）。本任务：
1. 拉取 ``status==pending && remind_at <= now()`` 的 reminder（最多 100 条/批）
2. 调当前 SubscribeMessageProvider（默认 stub，待微信模板审批后切 wechat）
3. 成功 → mark sent + sent_at + provider_message_id
4. 失败 → attempts += 1；attempts ≥ MAX_ATTEMPTS 时 lock 为 failed

幂等：每条只在 pending 时被取，转出 pending 即不会重派。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.followup_reminder import (
    MAX_ATTEMPTS,
    FollowupReminder,
    FollowupReminderStatus,
)
from app.repositories.followup_reminder import FollowupReminderRepository
from app.services.subscribe_message import (
    FollowupReminderPayload,
    SubscribeMessageProvider,
    get_subscribe_provider,
)

logger = logging.getLogger(__name__)

BATCH_SIZE = 100


async def _dispatch_one(
    session: AsyncSession,
    reminder: FollowupReminder,
    provider: SubscribeMessageProvider,
) -> dict:
    payload = FollowupReminderPayload(
        user_id=reminder.user_id,
        order_id=reminder.order_id,
        note=reminder.note,
    )
    repo = FollowupReminderRepository(session)
    try:
        result = await provider.send(payload)
    except Exception as exc:  # noqa: BLE001
        result = None
        err = f"provider raised: {exc!r}"
        attempts = reminder.attempts + 1
        new_status = (
            FollowupReminderStatus.failed
            if attempts >= MAX_ATTEMPTS
            else FollowupReminderStatus.pending
        )
        await repo.update(
            reminder,
            {"attempts": attempts, "last_error": err, "status": new_status},
        )
        return {"order_id": reminder.order_id, "outcome": new_status.value, "error": err}

    if result.success:
        await repo.update(
            reminder,
            {
                "status": FollowupReminderStatus.sent,
                "sent_at": datetime.now(timezone.utc),
                "provider_message_id": result.message_id,
                "last_error": None,
            },
        )
        return {"order_id": reminder.order_id, "outcome": "sent"}

    attempts = reminder.attempts + 1
    new_status = (
        FollowupReminderStatus.failed
        if attempts >= MAX_ATTEMPTS
        else FollowupReminderStatus.pending
    )
    await repo.update(
        reminder,
        {"attempts": attempts, "last_error": result.error, "status": new_status},
    )
    return {
        "order_id": reminder.order_id,
        "outcome": new_status.value,
        "error": result.error,
    }


async def _run(
    session: AsyncSession,
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    provider: SubscribeMessageProvider | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    provider = provider or get_subscribe_provider()
    repo = FollowupReminderRepository(session)
    due = await repo.list_due(now_fn(), limit=batch_size)
    sent = failed = retry = 0
    for reminder in due:
        outcome = await _dispatch_one(session, reminder, provider)
        if outcome["outcome"] == "sent":
            sent += 1
        elif outcome["outcome"] == "failed":
            failed += 1
        else:
            retry += 1
    return {"due": len(due), "sent": sent, "failed": failed, "retry": retry}


async def dispatch_followup_reminders(
    *,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    provider: SubscribeMessageProvider | None = None,
    batch_size: int = BATCH_SIZE,
) -> dict:
    """k8s CronJob / scheduler 入口。"""
    async with async_session() as session:
        result = await _run(
            session, now_fn=now_fn, provider=provider, batch_size=batch_size
        )
        await session.commit()
    logger.info("followup_reminder_dispatch result=%s", result)
    return result
