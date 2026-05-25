"""D-058: HTTP ``Idempotency-Key`` replay helper.

Used by write endpoints (currently ``POST /api/v1/orders``) to dedupe
client retries without leaking duplicate side effects.

Contract
--------
1. Endpoint reads ``request.headers.get("Idempotency-Key")``.
2. If absent → no replay attempted; proceed with original handler.
3. If present:
     * ``lookup(user_id, endpoint, key)`` → returns cached
       ``(status, body)`` tuple if a prior write with the same key has
       already been recorded. Endpoint replays it verbatim.
     * Otherwise endpoint runs the original handler, then calls
       ``store(user_id, endpoint, key, status, body)``.
4. Concurrent first-time writes with the same key are serialised by the
   ``UNIQUE (user_id, endpoint, key)`` constraint: the loser of the race
   catches ``IntegrityError``, re-reads the winner's row and replays it.

The cached body must be a JSON-serialisable mapping (typically the
endpoint's response body before ``Response`` wrapping).
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency_key import IdempotencyKey

logger = logging.getLogger(__name__)

# Cap stored response bodies so a pathological payload can't bloat the
# table. 64 KiB is plenty for any single API response we currently emit.
_MAX_BODY_BYTES = 64 * 1024


class IdempotencyService:
    """Thin wrapper around the ``idempotency_keys`` table."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lookup(
        self,
        *,
        user_id: uuid.UUID,
        endpoint: str,
        key: str,
    ) -> tuple[int, dict[str, Any]] | None:
        """Return cached ``(status, body_dict)`` for this key, or ``None``."""
        stmt = select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.endpoint == endpoint,
            IdempotencyKey.key == key,
        )
        row = (await self.session.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        try:
            body = json.loads(row.response_body)
        except json.JSONDecodeError:
            logger.error(
                "idempotency cache corrupt: id=%s user=%s endpoint=%s key=%s",
                row.id,
                user_id,
                endpoint,
                key,
            )
            return None
        return row.response_status, body

    async def store(
        self,
        *,
        user_id: uuid.UUID,
        endpoint: str,
        key: str,
        status: int,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Persist the response for this key.

        If a concurrent writer beat us to it (UNIQUE violation), we re-read
        their row and return **their** cached response so both clients see
        the same outcome.
        """
        body_str = json.dumps(body, default=str)
        if len(body_str.encode("utf-8")) > _MAX_BODY_BYTES:
            # Don't poison the table — surface as if no key was provided.
            logger.warning(
                "idempotency body too large (%d bytes) — skipping cache "
                "user=%s endpoint=%s key=%s",
                len(body_str),
                user_id,
                endpoint,
                key,
            )
            return status, body

        row = IdempotencyKey(
            user_id=user_id,
            endpoint=endpoint,
            key=key,
            response_status=status,
            response_body=body_str,
        )
        try:
            async with self.session.begin_nested():
                self.session.add(row)
                await self.session.flush()
        except IntegrityError:
            # Race: another request with the same key won. Replay theirs.
            logger.info(
                "idempotency race resolved by replay: user=%s endpoint=%s key=%s",
                user_id,
                endpoint,
                key,
            )
            cached = await self.lookup(
                user_id=user_id, endpoint=endpoint, key=key
            )
            if cached is not None:
                return cached
            # Extremely unlikely: row vanished between IntegrityError and
            # SELECT. Fall through and return the caller's response.
        return status, body
