"""OrderPrecheckAggregator — stub edition.

S3-DEV-005-CACHE-INVALIDATE ships **only** the skeleton: the public
``invalidate_and_recompute`` orchestrator, the ``_redis_del`` helper
(actually implemented, because it has no business logic — just a
Redis ``DEL``), and stubs for ``evaluate`` / ``_redis_set`` /
``_ws_broadcast`` that raise :class:`NotImplementedError`.

S3-DEV-003-PRECHECK-BACKEND will fill in:

* ``evaluate(order_id)`` — read 4 cards (contract / insurance / prep
  package / companion cert), compute the precheck summary, return a
  dict matching the design doc S3-trust-precheck-ui.md §3 contract.
* ``_redis_set(order_id, summary)`` — ``SET precheck:order:{order_id}
  <json> EX 300`` overwrite write per design line 224.
* ``_ws_broadcast(order_id, cards_changed)`` — push
  ``companion_cert_status_changed`` event to ws_room ``user:{user_id}``
  and ``companion:{cid}`` per 魈 Q2.

The orchestrator wiring is fixed here so PRECHECK-BACKEND only has to
fill the 3 stubs. The endpoint
(:mod:`app.api.v1.admin.cache_invalidate`) calls
``invalidate_and_recompute`` and the **endpoint contract** is stable:
the returned 200 shape stays the same once aggregator is real; until
then the orchestrator raises :class:`NotImplementedError` at the
``evaluate`` step and the endpoint maps that to a 501 response.

**DO NOT add evaluate logic in this task.** 魈 13:00Z 拍板 stub
boundary; expanding here is task-scope creep.
"""

from __future__ import annotations

from typing import Final, Sequence
from uuid import UUID

from redis.asyncio import Redis

# Cache key format per design S3-trust-precheck-ui.md line 224.
# Single key packs all 4 cards (魈 Q4 #4 — do NOT use per-card keys).
_CACHE_KEY_TEMPLATE: Final[str] = "precheck:order:{order_id}"


def _build_cache_key(order_id: UUID) -> str:
    """Compose the canonical precheck cache key.

    Returns a deterministic string the endpoint can include in the
    audit row + 200 response ``invalidated_keys`` field.
    """
    return _CACHE_KEY_TEMPLATE.format(order_id=str(order_id))


class OrderPrecheckAggregator:
    """Aggregator for 4 信任卡 precheck status (stub edition).

    Lifecycle:

    1. Endpoint calls :meth:`invalidate_and_recompute` with the order id
       and a (possibly None) list of cards.
    2. Aggregator runs :meth:`_redis_del` (defensive pre-invalidation).
       This is implemented here so post-DEL state is observable in tests
       even when ``evaluate`` is still stubbed.
    3. Aggregator runs :meth:`evaluate` — *stub raises*, the endpoint
       catches the exception, audits the partial-success, and returns
       **501 Not Implemented**.
    4. Once PRECHECK-BACKEND implements :meth:`evaluate`, the same
       orchestrator continues into :meth:`_redis_set` and
       :meth:`_ws_broadcast`, and the endpoint returns 200.

    The stub keeps ``_redis_del`` real because:

    * the endpoint can still claim the cache *was* defensively cleared
      (useful for manual ops drills during the stub window);
    * tests can assert real Redis state changed by the call;
    * design doc line 226 step 1 = "redis DEL ... 防御性 pre-invalidation"
      is a pure-Redis op with no aggregator-internal coupling, so
      shipping it here is cheap and zero-risk.
    """

    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def invalidate_and_recompute(
        self,
        order_id: UUID,
        cards: Sequence[str] | None = None,
    ) -> dict:
        """Public orchestrator — DEL → evaluate → SET → broadcast.

        Returns the 200 response body (``invalidated_keys`` + ``broadcast``)
        once fully wired. Until then, raises
        :class:`NotImplementedError` from the ``evaluate`` step; the
        endpoint catches and maps to 501.

        Parameters
        ----------
        order_id:
            UUID of the order whose precheck summary cache will be
            evicted + recomputed.
        cards:
            Optional list of card names for downstream filtering. The
            stub does not branch on cards; the parameter is only logged
            in the audit row (endpoint side) and forwarded to
            :meth:`_ws_broadcast` once implemented.
        """
        # Step 1 (real, ships in this task): defensive DEL.
        key = _build_cache_key(order_id)
        await self._redis_del(key)

        # Step 2 (stub): evaluate. Raises NotImplementedError; endpoint
        # catches + emits 501. PRECHECK-BACKEND replaces the body.
        summary = await self.evaluate(order_id)

        # Step 3 (stub): SET. Unreachable until evaluate is real.
        await self._redis_set(order_id, summary)

        # Step 4 (stub): WS broadcast. Unreachable until evaluate is real.
        broadcast_ok = await self._ws_broadcast(
            order_id,
            tuple(cards) if cards else None,
        )

        return {
            "invalidated_keys": [key],
            "broadcast": broadcast_ok,
        }

    async def _redis_del(self, key: str) -> int:
        """Defensive pre-invalidation. Real implementation, ships here.

        Wraps the Redis ``DEL`` so tests + ops drills can verify
        eviction even while the rest of the aggregator is stubbed.
        Returns the number of keys removed (0 if cache was cold).
        """
        return int(await self._redis.delete(key))

    async def evaluate(self, order_id: UUID) -> dict:  # noqa: ARG002 — stub
        """Read 4 cards + compute precheck summary. **Stub.**

        PRECHECK-BACKEND (S3-DEV-003-PRECHECK-BACKEND) must:

        * read order's contract / insurance / prep package /
          companion cert status from the respective tables;
        * apply ABAC 4-layer filtering (see design §5.3);
        * return a dict matching the OpenAPI schema in
          ``S3-trust-precheck-ui.md`` §3.

        Raises :class:`NotImplementedError` so the endpoint surfaces a
        deterministic 501 to admin clients during the stub window.
        """
        raise NotImplementedError(
            "OrderPrecheckAggregator.evaluate is implemented by "
            "S3-DEV-003-PRECHECK-BACKEND. Stub edition raises so the "
            "admin cache invalidate endpoint returns 501."
        )

    async def _redis_set(self, order_id: UUID, summary: dict) -> None:  # noqa: ARG002 — stub
        """SET precheck:order:{order_id} <summary> EX 300. **Stub.**"""
        raise NotImplementedError(
            "OrderPrecheckAggregator._redis_set is implemented by "
            "S3-DEV-003-PRECHECK-BACKEND."
        )

    async def _ws_broadcast(
        self,
        order_id: UUID,  # noqa: ARG002 — stub
        cards_changed: tuple[str, ...] | None,  # noqa: ARG002 — stub
    ) -> bool:
        """Push ``companion_cert_status_changed`` to ws_room. **Stub.**

        Targets per 魈 Q2: ``user:{user_id}`` + ``companion:{cid}``.
        Not ``admin`` (operator does not self-notify) and not group
        broadcast (order is 1-on-1).
        """
        raise NotImplementedError(
            "OrderPrecheckAggregator._ws_broadcast is implemented by "
            "S3-DEV-003-PRECHECK-BACKEND."
        )


__all__ = [
    "OrderPrecheckAggregator",
    "_build_cache_key",
]
