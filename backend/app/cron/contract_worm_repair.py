"""[S3-DEV-001-CONTRACT-WORM-COMPENSATION / ADR-0047 §5.2]

Contract WORM repair worker
---------------------------

Drains ``service_contracts`` rows in ``worm_status=pending_retry`` state,
calls ``_set_worm_policy_if_azure`` to re-apply Azure immutability policy.

Pattern mirrors ``contract_generate_pickup_job`` (acceptance #10 双层防线:
idempotent SELECT + scheduler-lock).

Defense layers:

1. **Idempotent retry**: ``_set_worm_policy_if_azure`` 重复调对 Azure 端
   是 idempotent (Locked policy + period_days 一致 → 服务端识别为同 policy
   不重复写). Local backend / Azure mock 路径恒成功.
2. **Scheduler lock**: ``acquire_scheduler_lock`` 保证多副本只一个 tick
   实际拿数据 (ADR-0035 §3 P1-A red line).
3. **Retry cap**: WORM_RETRY_CAP=3 retry 后 worm_status=permanently_failed
   + 高优 admin alert (alertmanager rule contract_worm_policy_failed
   {severity=high}).

Service 降级语义 (ADR-0047 §5.2):
- worm_status=pending_retry / permanently_failed 仍允许 ``get_contract_signed_url``
  (用户/陪诊师可看合同) — WORM 是审计层防护, 不阻业务读路径
- admin invalidate path 拒 ``permanently_failed`` 行 (审计完整性受损)

Cron 默认 enabled (与 generate_pickup 不同, 因为 worm repair 不会
产出"空合同副作用" — 仅 set policy 是幂等 no-op-on-success).

# 注: contract_storage._resolve_backend 路径假设
- LocalStorageBackend 路径: ``_set_worm_policy_if_azure`` 返 False (不 raise),
  cron 把行直接 mark applied (业务上无 WORM 概念).
- AzureBlobStorageBackend + immutability_enabled=False: 返 False, 同上.
- AzureBlobStorageBackend + immutability_enabled=True + 真 Azure SDK:
  Phase A mock 路径不 raise, 行 mark applied.
- AzureBlobStorageBackend + immutability_enabled=True + fault injection /
  Phase B 真 raise: ContractWormPolicyError → retry_count++.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.service_contract import (
    WORM_RETRY_CAP,
    ContractWormStatus,
    ServiceContract,
)
from app.services.contract_storage import (
    ContractWormPolicyError,
    _resolve_backend,
    _set_worm_policy_if_azure,
)
from app.utils.metrics import (
    contract_worm_policy_failed_total,
    contract_worm_repair_total,
)

logger = logging.getLogger("app.cron.contract_worm_repair")

CONTRACT_WORM_REPAIR_LOCK_KEY = "yiluan:scheduler:contract-worm-repair:lock"
CONTRACT_WORM_REPAIR_LOCK_TTL_SECONDS = 55


async def contract_worm_repair_job(app: Any = None) -> dict[str, Any]:
    """Scheduler-locked worker: drain WORM pending_retry ServiceContract rows.

    Returns ``{"status": "ok|skipped|disabled|error", "applied": int,
    "retry_again": int, "permanently_failed": int, "errors": int}`` for
    test assertions and operator visibility.

    Behavior:
      * If ``settings.contract_worm_repair_enabled`` is False (default True) →
        immediately return ``{"status": "disabled", ...}``. Cron scheduler 仍
        tick 但 job body skip.
      * 持 scheduler lock; SELECT 至多 ``contract_worm_repair_batch_size`` 行
        WHERE worm_status='pending_retry' ORDER BY worm_last_retry_at ASC NULLS FIRST.
      * 对每行调 ``_set_worm_policy_if_azure(backend, blob_path)``:
        - 成功 (返 True / 返 False 但 Local/mock backend) → worm_status=applied
          + metric contract_worm_repair_total{outcome="applied"}.
        - 抛 ContractWormPolicyError → worm_retry_count++, worm_last_retry_at=now:
          - count >= WORM_RETRY_CAP → worm_status=permanently_failed
            + metric contract_worm_repair_total{outcome="permanently_failed"}
            + metric contract_worm_policy_failed_total{stage="permanent_fail"}
            (alertmanager rule 会盯此 metric).
          - 否则 worm_status 保持 pending_retry, 等下一 tick
            + metric contract_worm_repair_total{outcome="retry_again"}
            + metric contract_worm_policy_failed_total{stage="repair_retry"}.
      * 单行失败不阻塞批次; 用 nested transaction (savepoint) 隔离每行.
    """
    if not getattr(settings, "contract_worm_repair_enabled", True):
        return {
            "status": "disabled",
            "applied": 0,
            "retry_again": 0,
            "permanently_failed": 0,
            "errors": 0,
        }

    redis_client = getattr(app.state, "redis", None) if app is not None else None
    applied = 0
    retry_again = 0
    permanently_failed = 0
    errors = 0

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=CONTRACT_WORM_REPAIR_LOCK_KEY,
                ttl=CONTRACT_WORM_REPAIR_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "contract_worm_repair: another instance holds the lock, skip"
                    )
                    return {
                        "status": "skipped",
                        "applied": 0,
                        "retry_again": 0,
                        "permanently_failed": 0,
                        "errors": 0,
                    }

                batch_size = getattr(settings, "contract_worm_repair_batch_size", 50)
                stmt = (
                    select(ServiceContract)
                    .where(
                        ServiceContract.worm_status == ContractWormStatus.pending_retry
                    )
                    .order_by(
                        # NULLS FIRST equiv: NULL worm_last_retry_at (从未 retry) 优先,
                        # 老的 retry 时间次之.
                        ServiceContract.worm_last_retry_at.asc().nulls_first()
                    )
                    .limit(batch_size)
                )
                rows = (await session.execute(stmt)).scalars().all()

                if not rows:
                    return {
                        "status": "ok",
                        "applied": 0,
                        "retry_again": 0,
                        "permanently_failed": 0,
                        "errors": 0,
                    }

                # 每行独立 try/except + 立即 commit; 一行失败不影响其余行.
                # ContractService.put_contract 已 commit blob; 这里只更新 row 字段.
                backend = _resolve_backend()
                from datetime import datetime
                from datetime import timezone as _tz

                for contract in rows:
                    if contract.storage_blob_path is None:
                        # 不应发生: worm_status=pending_retry 表示 blob 已写
                        # (put_contract 后的状态). 如果 blob_path=None 是 data
                        # corruption 或 manual SQL 改动, 记错继续.
                        logger.error(
                            "contract.worm_repair.row_blob_path_missing",
                            extra={
                                "contract_id": str(contract.id),
                                "worm_status": contract.worm_status.value,
                                "worm_retry_count": contract.worm_retry_count,
                            },
                        )
                        errors += 1
                        continue

                    try:
                        # 重新调用 _set_worm_policy_if_azure; 不 raise = 成功.
                        _set_worm_policy_if_azure(backend, contract.storage_blob_path)
                        # 成功 → worm_status=applied + worm_retry_count 保留 (审计).
                        contract.worm_status = ContractWormStatus.applied
                        contract.worm_last_retry_at = datetime.now(_tz.utc)
                        await session.flush()
                        applied += 1
                        contract_worm_repair_total.labels(outcome="applied").inc()
                        logger.info(
                            "contract.worm_repair.applied",
                            extra={
                                "contract_id": str(contract.id),
                                "blob_path": contract.storage_blob_path,
                                "previous_retry_count": contract.worm_retry_count,
                            },
                        )
                    except ContractWormPolicyError as exc:
                        # 失败 → retry_count++, 判是否超 cap.
                        contract.worm_retry_count = (contract.worm_retry_count or 0) + 1
                        contract.worm_last_retry_at = datetime.now(_tz.utc)
                        if contract.worm_retry_count >= WORM_RETRY_CAP:
                            contract.worm_status = ContractWormStatus.permanently_failed
                            permanently_failed += 1
                            contract_worm_repair_total.labels(
                                outcome="permanently_failed"
                            ).inc()
                            contract_worm_policy_failed_total.labels(
                                stage="permanent_fail"
                            ).inc()
                            logger.error(
                                "contract.worm_repair.permanently_failed",
                                extra={
                                    "contract_id": str(contract.id),
                                    "blob_path": contract.storage_blob_path,
                                    "retry_count": contract.worm_retry_count,
                                    "error": str(exc),
                                },
                                exc_info=exc,
                            )
                        else:
                            retry_again += 1
                            contract_worm_repair_total.labels(
                                outcome="retry_again"
                            ).inc()
                            contract_worm_policy_failed_total.labels(
                                stage="repair_retry"
                            ).inc()
                            logger.warning(
                                "contract.worm_repair.retry_again",
                                extra={
                                    "contract_id": str(contract.id),
                                    "blob_path": contract.storage_blob_path,
                                    "retry_count": contract.worm_retry_count,
                                    "cap": WORM_RETRY_CAP,
                                    "error": str(exc),
                                },
                            )
                        await session.flush()
                    except Exception as exc:  # pragma: no cover - safety net
                        # 未预期异常: 不修状态, 记错继续.
                        errors += 1
                        contract_worm_repair_total.labels(outcome="error").inc()
                        logger.error(
                            "contract.worm_repair.row_unexpected_error",
                            extra={"contract_id": str(contract.id)},
                            exc_info=exc,
                        )

                await session.commit()
    except Exception as exc:  # pragma: no cover - safety net
        logger.error("contract.worm_repair.batch_error", exc_info=exc)
        return {
            "status": "error",
            "applied": applied,
            "retry_again": retry_again,
            "permanently_failed": permanently_failed,
            "errors": errors,
        }

    return {
        "status": "ok",
        "applied": applied,
        "retry_again": retry_again,
        "permanently_failed": permanently_failed,
        "errors": errors,
    }


__all__ = [
    "CONTRACT_WORM_REPAIR_LOCK_KEY",
    "contract_worm_repair_job",
]
