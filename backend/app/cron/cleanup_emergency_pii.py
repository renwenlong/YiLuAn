"""ADR-0029 / D-043 — emergency PII 自动清理 cron。

每日 03:00 跑（schedule 参考 ``app/tasks/scheduler.py``，本任务也可由
OpenClaw cron / k8s CronJob 直接调度入口函数 ``cleanup_emergency_pii``）。

清理规则：

1. ``emergency_contacts`` 中 ``expires_at < now()`` → 硬删
   （用户主动删除时立即硬删，cron 仅处理 90d grace 后的尾扫）
2. ``emergency_events`` 中 ``triggered_at + 180d < now()`` → 硬删
   （PII 强保留期上限 180 天）
3. 写 audit 日志：
   ``action='cron_cleanup_emergency_pii'``,
   ``reason='{"contacts_deleted": N, "events_deleted": M}'``。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.admin_audit_log import AdminAuditLog
from app.models.emergency import EmergencyContact, EmergencyEvent

logger = logging.getLogger(__name__)

# Emergency event PII 强保留期上限（ADR-0029）
EMERGENCY_EVENT_RETENTION_DAYS = 180

# audit operator 标识：标记非用户触发
_CRON_OPERATOR = "cron:cleanup_emergency_pii"


async def _run(
    session: AsyncSession,
    *,
    now_fn: Callable[[], datetime],
    retention_days: int,
) -> dict:
    now = now_fn()
    event_cutoff = now - timedelta(days=retention_days)

    # 1) Contact: expires_at < now
    expired_contacts = (
        await session.execute(
            select(EmergencyContact.id).where(
                EmergencyContact.expires_at.is_not(None),
                EmergencyContact.expires_at < now,
            )
        )
    ).scalars().all()
    contacts_deleted = len(expired_contacts)
    if contacts_deleted:
        await session.execute(
            delete(EmergencyContact).where(EmergencyContact.id.in_(expired_contacts))
        )

    # 2) Event: triggered_at + 180d < now
    expired_events = (
        await session.execute(
            select(EmergencyEvent.id).where(
                EmergencyEvent.triggered_at < event_cutoff,
            )
        )
    ).scalars().all()
    events_deleted = len(expired_events)
    if events_deleted:
        await session.execute(
            delete(EmergencyEvent).where(EmergencyEvent.id.in_(expired_events))
        )

    # 3) audit
    if contacts_deleted or events_deleted:
        audit = AdminAuditLog(
            target_type="emergency",
            target_id=uuid.UUID(int=0),  # 系统级，无单一目标
            action="cron_cleanup_emergency_pii",
            operator=_CRON_OPERATOR,
            reason=json.dumps(
                {
                    "contacts_deleted": contacts_deleted,
                    "events_deleted": events_deleted,
                    "ran_at": now.isoformat(),
                },
                ensure_ascii=False,
            ),
        )
        session.add(audit)
    await session.flush()

    return {
        "status": "ok",
        "contacts_deleted": contacts_deleted,
        "events_deleted": events_deleted,
    }


async def cleanup_emergency_pii(
    *,
    session: AsyncSession | None = None,
    now_fn: Callable[[], datetime] | None = None,
    retention_days: int = EMERGENCY_EVENT_RETENTION_DAYS,
) -> dict:
    """ADR-0029 / D-043 cron 入口。

    - ``session``: 测试可注入；生产传 None 时自建 ``async_session``。
    - ``now_fn``: 测试可注入 fake clock。
    - ``retention_days``: 事件保留期，默认 180 天。

    Returns: ``{"status": "ok"|"error", "contacts_deleted": N, "events_deleted": M}``。
    """
    _now = now_fn or (lambda: datetime.now(timezone.utc))

    try:
        if session is not None:
            result = await _run(session, now_fn=_now, retention_days=retention_days)
            await session.commit()
            return result

        async with async_session() as s:
            try:
                result = await _run(s, now_fn=_now, retention_days=retention_days)
                await s.commit()
                return result
            except Exception:
                await s.rollback()
                raise
    except Exception as exc:
        logger.exception("cleanup_emergency_pii failed: %s", exc)
        return {"status": "error", "contacts_deleted": 0, "events_deleted": 0}
