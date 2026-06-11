"""Broadcast facade for precheck-status WebSocket events — S3-DEV-003 c4.

This module is the single entrypoint c5 hooks call to push precheck
state changes to subscribed WebSocket clients. The WS endpoint itself
lives in :mod:`app.api.v1.ws` (``/ws/v1/orders/{order_id}/precheck``);
this facade hides the broker plumbing so the after-commit hooks in c5
do not need to know about ``WsPubSubBroker`` lifecycle.

Design refs:

- ``docs/design/S3-trust-precheck-ui.md`` §4.3 (3 broadcast events)
- ``docs/design/S3-trust-precheck-ui.md`` §5 (WS handler contract)
- task ``S3-DEV-003-PRECHECK-BACKEND`` AC#3 (3 event shapes)

Broker reuse decision (c4 KISS):

- Reuses :class:`app.ws.pubsub.WsPubSubBroker` with
  ``key_field="order_id"`` and an in-memory fallback broker (no Redis
  pubsub) for single-replica deployments. Multi-replica cross-fanout
  via Redis ``channel="ws:precheck"`` is left to c5 / ops (mirrors the
  chat / share broker bootstrap pattern in :mod:`app.main`).
- A dedicated ``PrecheckBroker`` class would duplicate the existing
  broker without adding behaviour, so we deliberately do **not** add
  one. (Reviewer note: if c5 needs precheck-specific dedup or replay
  logic, revisit then.)

Event shapes (frozen by AC#3):

- ``precheck.status.updated`` — one card state changed
- ``precheck.all_ready`` — all 4 cards green
- ``precheck.blocked`` — at least one card red with explicit reason
"""

from __future__ import annotations

import datetime
import logging
from typing import Any
from uuid import UUID

from fastapi import FastAPI

from app.ws.pubsub import WsPubSubBroker

logger = logging.getLogger(__name__)

# Redis pubsub channel name reserved for precheck cross-replica fanout.
# Currently unused (in-memory fallback only); c5 / ops can wire this up
# via the same start_ws_pubsub bootstrap pattern as chat / share.
PRECHECK_PUBSUB_CHANNEL = "ws:precheck"

# Module-level fallback broker, mirroring _fallback_chat_broker in
# ``app.api.v1.ws``. Lazily initialised so tests that never import the
# WS endpoint do not pay broker setup cost.
_fallback_precheck_broker: WsPubSubBroker | None = None


def get_or_create_precheck_broker(app: FastAPI) -> WsPubSubBroker:
    """Return the precheck broker bound to ``app``, creating an
    in-memory fallback if no Redis-backed broker has been installed.

    Resolution order (mirrors chat broker):

    1. ``app.state.ws_precheck_broker`` if set by a Redis-pubsub
       bootstrap (future c5 / ops work).
    2. Module-level fallback singleton with ``redis_client=None``.
    """
    broker = getattr(app.state, "ws_precheck_broker", None)
    if broker is not None:
        return broker

    global _fallback_precheck_broker
    if _fallback_precheck_broker is None:
        _fallback_precheck_broker = WsPubSubBroker(
            redis_client=None,
            enabled=False,
            channel=PRECHECK_PUBSUB_CHANNEL,
            key_field="order_id",
        )
        _fallback_precheck_broker._started = True  # type: ignore[attr-defined]
    return _fallback_precheck_broker


def _now_iso() -> str:
    """UTC ISO-8601 timestamp with explicit ``Z`` suffix."""
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


async def broadcast_status_updated(
    app: FastAPI,
    order_id: UUID,
    *,
    card: str,
    status: dict[str, Any],
    all_ready: bool,
) -> None:
    """Push a ``precheck.status.updated`` event for one card.

    Local delivery + Redis fanout (when configured) are best-effort.
    Per-client send errors and Redis publish errors are swallowed +
    logged inside the broker; this facade only logs broker-level
    exceptions (rare; defensive only).
    """
    broker = get_or_create_precheck_broker(app)
    payload = {
        "event": "precheck.status.updated",
        "order_id": str(order_id),
        "card": card,
        "status": status,
        "all_ready": all_ready,
        "ts": _now_iso(),
    }
    await _publish(broker, order_id, payload, event_name="status.updated")


async def broadcast_all_ready(app: FastAPI, order_id: UUID) -> None:
    """Push a ``precheck.all_ready`` event (4 cards green terminal state)."""
    broker = get_or_create_precheck_broker(app)
    payload = {
        "event": "precheck.all_ready",
        "order_id": str(order_id),
        "ts": _now_iso(),
    }
    await _publish(broker, order_id, payload, event_name="all_ready")


async def broadcast_blocked(
    app: FastAPI,
    order_id: UUID,
    *,
    reason: str,
) -> None:
    """Push a ``precheck.blocked`` event with an explicit human-readable reason."""
    broker = get_or_create_precheck_broker(app)
    payload = {
        "event": "precheck.blocked",
        "order_id": str(order_id),
        "reason": reason,
        "ts": _now_iso(),
    }
    await _publish(broker, order_id, payload, event_name="blocked")


async def _publish(
    broker: WsPubSubBroker,
    order_id: UUID,
    payload: dict[str, Any],
    *,
    event_name: str,
) -> None:
    """Common publish path with structured logging on failure.

    ``push_to_key`` already swallows per-client send errors and Redis
    publish errors; this wrapper only catches broker-level exceptions
    (which would be a defect rather than expected behaviour).
    """
    try:
        await broker.push_to_key(order_id, payload)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "precheck broadcast failed",
            extra={
                "event": f"precheck.{event_name}",
                "order_id": str(order_id),
                "error": str(exc),
            },
        )
