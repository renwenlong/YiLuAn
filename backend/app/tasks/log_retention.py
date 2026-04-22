"""日志保留清理 job（D-027 / TD-OPS-02）。

定期清理过期的 payment_callback_log 和 sms_send_log 记录。
两张表都有 ``expires_at`` 字段（应用层写入时填 ``now() + 90d``）。

清理策略：
- ``expires_at IS NOT NULL AND expires_at < now()``  → 直接删除
- ``expires_at IS NULL AND created_at < now() - fallback_days`` → 兜底删除
  （兼容 expires_at 字段上线前的历史数据）

使用 PG advisory lock 防止多副本并发执行。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, and_

from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.payment_callback_log import PaymentCallbackLog
from app.models.sms_send_log import SmsSendLog

logger = logging.getLogger(__name__)

# 默认保留天数（用于 expires_at 为 NULL 的历史记录兜底）
DEFAULT_RETENTION_DAYS = 90

# 每次批量删除上限，避免长事务
BATCH_SIZE = 5000

# Advisory lock keys
PAYMENT_LOG_CLEANUP_LOCK_KEY = "yiluan:scheduler:payment-log-cleanup:lock"
SMS_LOG_CLEANUP_LOCK_KEY = "yiluan:scheduler:sms-log-cleanup:lock"
LOCK_TTL_SECONDS = 120


async def cleanup_payment_callback_log(
    app=None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict:
    """删除过期的 payment_callback_log 记录。

    Returns:
        {"status": "ok"|"skipped"|"error", "deleted": int}
    """
    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=PAYMENT_LOG_CLEANUP_LOCK_KEY,
                ttl=LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug("cleanup_payment_callback_log: lock held by another instance, skip")
                    return {"status": "skipped", "deleted": 0}

                try:
                    now = datetime.now(timezone.utc)
                    cutoff = now - timedelta(days=retention_days)

                    stmt = (
                        delete(PaymentCallbackLog)
                        .where(
                            or_(
                                and_(
                                    PaymentCallbackLog.expires_at.isnot(None),
                                    PaymentCallbackLog.expires_at < now,
                                ),
                                and_(
                                    PaymentCallbackLog.expires_at.is_(None),
                                    PaymentCallbackLog.created_at < cutoff,
                                ),
                            )
                        )
                        .execution_options(synchronize_session=False)
                    )
                    result = await session.execute(stmt)
                    deleted = result.rowcount
                    await session.commit()

                    logger.info(
                        "cleanup_payment_callback_log: deleted %d rows (retention=%dd)",
                        deleted,
                        retention_days,
                    )
                    return {"status": "ok", "deleted": deleted}
                except Exception:
                    await session.rollback()
                    raise
    except Exception as exc:
        logger.exception("cleanup_payment_callback_log failed: %s", exc)
        return {"status": "error", "deleted": 0}


async def cleanup_sms_send_log(
    app=None,
    retention_days: int = DEFAULT_RETENTION_DAYS,
) -> dict:
    """删除过期的 sms_send_log 记录。

    Returns:
        {"status": "ok"|"skipped"|"error", "deleted": int}
    """
    redis_client = None
    if app is not None:
        redis_client = getattr(app.state, "redis", None)

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=SMS_LOG_CLEANUP_LOCK_KEY,
                ttl=LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug("cleanup_sms_send_log: lock held by another instance, skip")
                    return {"status": "skipped", "deleted": 0}

                try:
                    now = datetime.now(timezone.utc)
                    cutoff = now - timedelta(days=retention_days)

                    stmt = (
                        delete(SmsSendLog)
                        .where(
                            or_(
                                and_(
                                    SmsSendLog.expires_at.isnot(None),
                                    SmsSendLog.expires_at < now,
                                ),
                                and_(
                                    SmsSendLog.expires_at.is_(None),
                                    SmsSendLog.created_at < cutoff,
                                ),
                            )
                        )
                        .execution_options(synchronize_session=False)
                    )
                    result = await session.execute(stmt)
                    deleted = result.rowcount
                    await session.commit()

                    logger.info(
                        "cleanup_sms_send_log: deleted %d rows (retention=%dd)",
                        deleted,
                        retention_days,
                    )
                    return {"status": "ok", "deleted": deleted}
                except Exception:
                    await session.rollback()
                    raise
    except Exception as exc:
        logger.exception("cleanup_sms_send_log failed: %s", exc)
        return {"status": "error", "deleted": 0}
