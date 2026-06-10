"""User-side precheck-status GET endpoint — S3-DEV-003 c3.

This module implements the polling fallback / first-paint endpoint for
the 4 信任卡 precheck UI. WebSocket push handler is c4 (separate file).

Design refs:

- ``docs/design/S3-trust-precheck-ui.md`` §5.2 (endpoint behaviour)
- ``docs/design/S3-trust-precheck-ui.md`` §5.3 (ABAC 4 layers)
- ADR-0048 §7.0 (ABAC defence-in-depth template)
- task ``S3-DEV-003-PRECHECK-BACKEND`` AC#2

ABAC layer mapping (this file = endpoint layer; aggregator = service layer):

- Layer 1 (Schema) — :class:`OrderPrecheckSummaryView` declares
  ``extra='forbid'`` and does NOT define any of the 17 negative-list
  fields. Implemented in c1.
- Layer 2 (Endpoint role) — :func:`get_precheck_status` uses
  :class:`CurrentPatient` so admin / companion JWTs receive 403.
  Additionally, order owner (``Order.patient_id == user.id``) is
  enforced before any aggregator call to keep cross-patient queries
  from leaking the existence of an order.
- Layer 3 (Service SELECT projection) — handled inside
  :class:`OrderPrecheckAggregator` (c2): each ``_load_*`` SELECTs only
  positive-list columns, never raw blob / hash / underwriter / PII.
- Layer 4 (Test sentinels) — schema dump assertions (c1) + endpoint
  integration tests in this PR + Schemathesis positive list (c5).

Cache policy (design §5.3 + AC#2 SLO):

- Read-through cache: first check ``precheck:order:{order_id}`` Redis
  key; HIT → return cached JSON (P95 ≤200ms).
- Cache MISS → call :meth:`OrderPrecheckAggregator.evaluate` which
  performs the 4 SELECTs + signed-URL signing + masking, then writes
  the result back to Redis with TTL 5 min (P95 ≤800ms).
- Write-through invalidation (DEL → evaluate → SET) is performed by
  the 4 after_commit hooks in c5 + the admin manual invalidate
  endpoint (already shipped in c2); this endpoint never DELetes the
  cache itself.

Owner-check semantics (open question pending 魈 ack):

- Option A (design §5.2 文字): order exists but not owner → 403.
- Option B (codebase precedent in ``prep_packages_users.py``): not
  owner → 404 to avoid order_id enumeration.
- Option C (hybrid, current implementation): not owner → 404 from
  the endpoint's perspective, internal logger.info records the
  ABAC-mismatch reason for audit; symmetric with prep_packages_users.

The hybrid option is the chosen default until 魈 picks differently;
it matches the symmetric handling of admin / companion roles where
the endpoint-level role gate (``CurrentPatient``) still returns 403
to keep ABAC Layer 2 semantics explicit.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.openapi_meta import err
from app.core.redis import get_redis
from app.dependencies import CurrentPatient, DBSession
from app.models.order import Order
from app.schemas.order_precheck import OrderPrecheckSummaryView
from app.services.order_precheck_aggregator import (
    OrderPrecheckAggregator,
    _build_cache_key,
)

logger = logging.getLogger(__name__)

# Symmetric with admin / companions routers — single user-facing tag
# so OpenAPI groups precheck-status next to other user-side endpoints.
router = APIRouter(prefix="/users/orders", tags=["users-precheck"])


async def _get_aggregator(
    redis: Annotated[Redis, Depends(get_redis)],
    session: DBSession,
) -> OrderPrecheckAggregator:
    """FastAPI dependency that wires the aggregator with per-request
    Redis + DB session — c2 lifecycle contract.
    """
    return OrderPrecheckAggregator(redis=redis, session=session)


async def _assert_order_owner_or_404(
    session: AsyncSession,
    order_id: UUID,
    user_id: UUID,
) -> None:
    """ABAC Layer 2.5 — order-owner gate.

    Hybrid option C: any failure (order missing OR order exists with
    different patient_id) returns 404, never 403, to prevent order_id
    enumeration. The patient-role gate (``CurrentPatient``) above
    already raises 403 for admin / companion JWTs so ABAC Layer 2
    role-distinction stays observable.

    SELECTs only the ``patient_id`` column — full ``Order`` row is not
    needed and would widen the negative-list surface unnecessarily.
    """
    stmt = select(Order.patient_id).where(Order.id == order_id)
    result = await session.execute(stmt)
    patient_id = result.scalar_one_or_none()
    if patient_id is None:
        logger.info(
            "precheck-status 404: order missing",
            extra={"order_id": str(order_id), "user_id": str(user_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order not found",
        )
    if patient_id != user_id:
        logger.info(
            "precheck-status 404: ABAC owner-mismatch (hybrid 404 mask)",
            extra={
                "order_id": str(order_id),
                "user_id": str(user_id),
                "true_owner_id": str(patient_id),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="order not found",
        )


@router.get(
    "/{order_id}/precheck-status",
    response_model=OrderPrecheckSummaryView,
    summary="患者获取订单 4 信任卡 precheck 状态 (合同 / 保险 / AI 准备包 / 陪诊师资质)",
    description=(
        "首屏 + polling fallback 端点 (5s 间隔). WebSocket 实时推送走 "
        "``GET /ws/v1/orders/{order_id}/precheck`` (c4). "
        "Cache hit P95 ≤200ms / miss ≤800ms. "
        "ABAC: patient role only; admin/companion 401/403; 跨订单 404. "
        "脱敏: policy_no 头4+****+尾4; signed URL TTL ≤15min."
    ),
    responses={**err(401, 403, 404, 500)},
)
async def get_precheck_status(
    order_id: UUID,
    current_user: CurrentPatient,
    session: DBSession,
    redis: Annotated[Redis, Depends(get_redis)],
    aggregator: Annotated[OrderPrecheckAggregator, Depends(_get_aggregator)],
) -> OrderPrecheckSummaryView:
    """Return the aggregated 4-card precheck status for ``order_id``.

    Flow (design §5.2 + AC#2):

    1. ``CurrentPatient`` dependency rejects admin / companion JWTs
       (Layer 2 role gate, 401 if no token, 403 if non-patient role).
    2. :func:`_assert_order_owner_or_404` enforces order ownership;
       missing order or owner-mismatch → 404 (防 enum).
    3. Cache read-through: ``GET precheck:order:{order_id}``.
       - HIT → parse JSON, return :class:`OrderPrecheckSummaryView`.
       - MISS → call ``aggregator.evaluate(order_id)``, which writes
         the result back to cache with TTL 5 min and returns the dict
         we serialise into the view.

    The aggregator's per-card SELECTs (Layer 3) are the only place
    negative-list fields could leak; they project explicit positive
    columns and never the full row.
    """
    # ABAC Layer 2.5: order owner gate (hybrid 404).
    await _assert_order_owner_or_404(session, order_id, current_user.id)

    # Cache read-through (HIT path, target P95 ≤200ms).
    cache_key = _build_cache_key(order_id)
    cached = await redis.get(cache_key)
    if cached is not None:
        try:
            return OrderPrecheckSummaryView.model_validate_json(cached)
        except Exception as exc:  # pragma: no cover - defensive
            # Corrupt cache (schema drift across deploys) — log and fall
            # through to recompute path so the request still succeeds.
            logger.warning(
                "precheck-status: cache parse failure, recomputing",
                extra={"order_id": str(order_id), "error": str(exc)},
            )

    # Cache MISS path (target P95 ≤800ms): aggregator.evaluate runs
    # 4 SELECTs + signed-URL + masking; this endpoint then SETs the
    # cache (TTL 5 min) so subsequent polls within the window hit the
    # fast path. We replicate the SET here rather than inside
    # ``evaluate`` because c2 intentionally keeps the aggregator
    # cache-free — the admin invalidate endpoint owns DEL→evaluate→SET
    # so it can ack with the freshly computed body; here we own SET
    # on the read path.
    summary_dict = await aggregator.evaluate(order_id)
    summary_view = OrderPrecheckSummaryView.model_validate(summary_dict)
    await redis.set(
        cache_key,
        summary_view.model_dump_json(),
        ex=300,  # 5 min TTL per design §5.3 / AC#4
    )
    return summary_view


__all__ = ["router"]
