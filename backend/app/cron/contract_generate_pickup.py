"""[S3-DEV-001-CONTRACT-PICKUP-CRON / ADR-0046 §3.x]

Contract generate pickup worker
-------------------------------

Drains ``service_contracts`` rows in ``pending_generation`` state, calls
``ContractService.generate_now(contract.id)`` to render PDF + WORM-put +
flip to ``active``. Mirrors ``ai_summary_enqueue.process_pending_digests_job``
pattern (acceptance #10 双层防线: idempotent enqueue + scheduler-lock).

Defense layers:

1. **Enqueue idempotency**: ``service_contracts.order_id`` is UNIQUE +
   ``contract_hash`` is UNIQUE. ``ContractService.request_generation``
   catches IntegrityError and returns existing row — 重复 accept
   (不可能) 仍只一行.
2. **Scheduler lock**: ``acquire_scheduler_lock`` guarantees only one
   replica processes the batch per tick (ADR-0035 §3 P1-A red line).
   Even if two replicas tick the same millisecond, only one actually picks.

# Cron 默认 disabled (魈 EVENT-WIRING 拍板)

``settings.contract_generate_pickup_enabled = False`` (默认).
原因: CORE PR 合并后, ``ContractService._render_pdf`` 仍是 stub
(14 字节合法 PDF). 若 cron 启动, ``generate_now`` 会写 14 字节
"空合同" — storage 层能过 (合法 PDF magic byte), 但业务上空文档不能
接收.

PDF-RENDER task (uuid ``33ac1174``) 实装真渲染后, 通过 env 改
``CONTRACT_GENERATE_PICKUP_ENABLED=true`` 才开启. scheduler.py 依然
注册 job, 但 job body 检查 flag 后直接 skip — 避免 "scheduler 启动后
不需重启即可开启" 运维体验.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import settings
from app.core.distributed_lock import acquire_scheduler_lock
from app.database import async_session
from app.models.service_contract import ContractStatus, ServiceContract
from app.services.contract_service import (
    ContractGenerateNowError,
    ContractService,
)

logger = logging.getLogger("app.cron.contract_generate_pickup")

CONTRACT_GENERATE_PICKUP_LOCK_KEY = "yiluan:scheduler:contract-generate-pickup:lock"
CONTRACT_GENERATE_PICKUP_LOCK_TTL_SECONDS = 55


async def contract_generate_pickup_job(app: Any = None) -> dict[str, Any]:
    """Scheduler-locked worker: drain pending_generation ServiceContract rows.

    Returns ``{"status": "ok|skipped|disabled|error", "processed": int,
    "failed": int}`` for test assertions and operator visibility.

    Behavior:
      * If ``settings.contract_generate_pickup_enabled`` is False → immediately
        return ``{"status": "disabled", "processed": 0, "failed": 0}``. The
        scheduler still ticks but no DB / lock work happens.
      * Otherwise, take scheduler lock; load up to
        ``contract_generate_pickup_batch_size`` rows ORDER BY ``updated_at ASC``
        (oldest first); for each, call ``ContractService.generate_now``.
      * Failures are logged + counted but do **not** abort the batch —
        ``generate_now`` itself marks the row as ``generation_failed`` and
        writes ``last_error_trace`` so compensation cron can retry.
    """
    if not settings.contract_generate_pickup_enabled:
        # 默认 disabled — CORE PR 合并后 cron 仍不跑, 避免 stub PDF 写入 storage.
        return {"status": "disabled", "processed": 0, "failed": 0}

    redis_client = getattr(app.state, "redis", None) if app is not None else None
    processed = 0
    failed = 0

    try:
        async with async_session() as session:
            lock = acquire_scheduler_lock(
                session=session,
                redis_client=redis_client,
                key=CONTRACT_GENERATE_PICKUP_LOCK_KEY,
                ttl=CONTRACT_GENERATE_PICKUP_LOCK_TTL_SECONDS,
            )
            async with lock:
                if not lock.acquired:
                    logger.debug(
                        "contract_generate_pickup: another instance holds the lock, skip"
                    )
                    return {"status": "skipped", "processed": 0, "failed": 0}

                stmt = (
                    select(ServiceContract)
                    .where(
                        ServiceContract.status == ContractStatus.pending_generation
                    )
                    .order_by(ServiceContract.updated_at.asc())
                    .limit(settings.contract_generate_pickup_batch_size)
                )
                rows = (await session.execute(stmt)).scalars().all()

                if not rows:
                    return {"status": "ok", "processed": 0, "failed": 0}

                contract_service = ContractService(session=session)
                for contract in rows:
                    try:
                        await contract_service.generate_now(contract.id)
                        processed += 1
                    except ContractGenerateNowError as exc:
                        # generate_now 已在内部写 generation_failed +
                        # last_error_trace, 这里仅计数 + 继续处理下一行.
                        failed += 1
                        logger.warning(
                            "contract.generate_pickup.row_failed",
                            extra={
                                "contract_id": str(contract.id),
                                "error": str(exc),
                            },
                        )
                    except Exception as exc:  # pragma: no cover - safety net
                        # Unexpected — cron 不能被单行心得堆, 记日志继续.
                        failed += 1
                        logger.error(
                            "contract.generate_pickup.row_unexpected_error",
                            extra={"contract_id": str(contract.id)},
                            exc_info=exc,
                        )

                await session.commit()
    except Exception as exc:  # pragma: no cover - safety net
        logger.error("contract.generate_pickup.batch_error", exc_info=exc)
        return {"status": "error", "processed": processed, "failed": failed}

    return {"status": "ok", "processed": processed, "failed": failed}


__all__ = [
    "CONTRACT_GENERATE_PICKUP_LOCK_KEY",
    "contract_generate_pickup_job",
]
