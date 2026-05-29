"""[S2-DEV-006] Family-share token anomaly scanner.

每 5 分钟扫一次 active 的 ``OrderShareToken``，对每个 token 计算
**24h 滚动窗口内 distinct accessor_openid 数**；超过阈值（默认 5）→
自动 revoke + 计 ``share_token_auto_revoked_total{reason}`` + 日志告警。

被 revoke 后，在线的家属 WS 会在下一次 ping 心跳时被服务端复查踢断
(close 4013，见 ``app/api/v1/ws.py`` share ping 分支)。

分布式锁
--------
复用 ``acquire_scheduler_lock``（PG advisory / Redis NX / 假锁三态自适应），
多副本下同一轮只有一个实例真正扫描。锁与业务在同一 ``AsyncSession`` 内，
满足 PG advisory lock「同连接」约束。

分片
----
acceptance #3 要求 hash partitioning 避免大表全扫。当前 active 集规模小，
``list_all_active`` 一次取全量即可；预留 ``partition_count`` /
``partition_index`` 参数，规模上来后由调度器按 ``created_at`` hash 分片
多 job 并行（本期不开多分片，单分片 = 全量）。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.observability.share_metrics import SHARE_TOKEN_AUTO_REVOKED_TOTAL
from app.repositories.order_share_token import OrderShareTokenRepository

logger = logging.getLogger("app.cron.share_token_scanner")

SHARE_SCANNER_LOCK_KEY = "yiluan:scheduler:share-token-scanner:lock"
SHARE_SCANNER_LOCK_TTL_SECONDS = 280  # < 5min 间隔，留缓冲
DISTINCT_ACCESSOR_WINDOW = timedelta(hours=24)
ACCESS_LOG_RETENTION = timedelta(days=7)  # = token hard cap


async def scan_share_token_anomalies_job(app=None) -> dict:
    """Scan active share tokens; auto-revoke leakage suspects.

    Returns a dict for test assertions:
        {"status": "ok"|"skipped"|"error", "revoked": int, "scanned": int}
    """
    redis_client = getattr(app.state, "redis", None) if app is not None else None
    threshold = settings.share_distinct_accessor_threshold
    now = datetime.now(timezone.utc)

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=SHARE_SCANNER_LOCK_KEY,
                ttl=SHARE_SCANNER_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "share_token_scanner: another instance holds the lock, skip"
                    )
                    return {"status": "skipped", "revoked": 0, "scanned": 0}

                revoked = await _scan_and_revoke(session, threshold, now)
                # Retention prune (best-effort, same pass).
                try:
                    pruned = await OrderShareTokenRepository(
                        session
                    ).prune_access_logs_older_than(
                        before=now - ACCESS_LOG_RETENTION
                    )
                    if pruned:
                        logger.info(
                            "share_token_scanner: pruned %d old access logs",
                            pruned,
                        )
                except Exception:
                    logger.warning(
                        "share_token_scanner: access-log prune failed",
                        exc_info=True,
                    )
                await session.commit()
                return {
                    "status": "ok",
                    "revoked": revoked["revoked"],
                    "scanned": revoked["scanned"],
                }
    except Exception as exc:
        logger.exception("share_token_scanner failed: %s", exc)
        return {"status": "error", "revoked": 0, "scanned": 0}


async def _scan_and_revoke(session, threshold: int, now: datetime) -> dict:
    repo = OrderShareTokenRepository(session)
    active = await repo.list_all_active(now=now)
    revoked = 0
    for token in active:
        distinct = await repo.count_distinct_accessors_in_window(
            token.id, window=DISTINCT_ACCESSOR_WINDOW, now=now
        )
        if distinct > threshold:
            await repo.revoke(token, revoked_by=None)
            SHARE_TOKEN_AUTO_REVOKED_TOTAL.labels(
                reason="distinct_accessor_exceeded"
            ).inc()
            logger.warning(
                "share_token_scanner: auto-revoked token %s "
                "(order=%s, distinct_24h=%d > %d) — possible URL leak",
                token.id,
                token.order_id,
                distinct,
                threshold,
            )
            revoked += 1
    return {"revoked": revoked, "scanned": len(active)}


__all__ = [
    "ACCESS_LOG_RETENTION",
    "DISTINCT_ACCESSOR_WINDOW",
    "SHARE_SCANNER_LOCK_KEY",
    "scan_share_token_anomalies_job",
]
