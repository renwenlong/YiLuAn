"""Shared FastAPI dependencies for the precheck-status feature.

S3-DEV-003 c4 promotion: extracted from
``backend/app/api/v1/users_precheck.py`` (c3) so the WebSocket handler
introduced in c4 can reuse the same aggregator wiring and ABAC owner
gate without importing from a sibling endpoint module.

Design refs:

- ``docs/design/S3-trust-precheck-ui.md`` §5.2 / §5.3
- ADR-0048 §7.0 (ABAC defence-in-depth)
- c3 review note from 魈: promote ``_get_aggregator`` once a second
  caller appears — c4 WS handler is that second caller.

This module owns **only** dependency wiring + the ABAC owner gate
helper that both the polling endpoint and the WS handshake need.
Nothing here issues HTTP responses directly; the WS handler maps
``OwnerCheckFailure`` to a close code (4003), while the REST endpoint
re-raises ``HTTPException(404)`` to keep the hybrid-404 enumeration
mask intact.
"""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.dependencies import DBSession
from app.models.order import Order
from app.services.order_precheck_aggregator import OrderPrecheckAggregator

logger = logging.getLogger(__name__)


async def get_precheck_aggregator(
    redis: Annotated[Redis, Depends(get_redis)],
    session: DBSession,
) -> OrderPrecheckAggregator:
    """FastAPI dependency that wires the aggregator with per-request
    Redis + DB session — c2 lifecycle contract.

    Promoted from ``users_precheck._get_aggregator`` in c4 so both the
    GET endpoint and the WS handler share a single source of truth.
    """
    return OrderPrecheckAggregator(redis=redis, session=session)


class OwnerCheckFailure(Exception):
    """ABAC Layer 2.5 owner-gate failure (raised by
    :func:`load_order_owner_id`).

    Caller (REST endpoint or WS handler) decides the user-visible
    failure mode:

    - REST endpoint → ``HTTPException(404)`` hybrid mask (c3 behaviour
      preserved by :func:`assert_order_owner_or_404`).
    - WS handler → ``websocket.close(code=4003)`` because WS handshake
      already established a valid JWT, so leaking "this order_id does
      not match you" via 4003 is acceptable and consistent with the
      ``/ws/chat/{order_id}`` pattern.
    """


async def load_order_owner_id(
    session: AsyncSession,
    order_id: UUID,
) -> UUID:
    """Return ``Order.patient_id`` for ``order_id``.

    SELECTs only the ``patient_id`` column to keep the negative-list
    surface tight (no need to materialise the full ``Order`` row).

    Raises :class:`OwnerCheckFailure` if the order is missing — caller
    decides whether to mask as 404 or close the WS.
    """
    stmt = select(Order.patient_id).where(Order.id == order_id)
    result = await session.execute(stmt)
    patient_id = result.scalar_one_or_none()
    if patient_id is None:
        raise OwnerCheckFailure("order not found")
    return patient_id


async def assert_order_owner_or_404(
    session: AsyncSession,
    order_id: UUID,
    user_id: UUID,
) -> None:
    """REST-style ABAC Layer 2.5 owner gate (c3 hybrid-404 mask).

    Hybrid option C: any failure (order missing OR order exists with
    different patient_id) returns 404, never 403, to prevent order_id
    enumeration. The patient-role gate (``CurrentPatient``) above the
    caller already raises 403 for admin / companion JWTs so ABAC
    Layer 2 role-distinction stays observable.

    Promoted from ``users_precheck._assert_order_owner_or_404`` in c4
    with the loader split out so the WS handler can reuse the SELECT
    while choosing its own failure mode.
    """
    try:
        patient_id = await load_order_owner_id(session, order_id)
    except OwnerCheckFailure:
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
