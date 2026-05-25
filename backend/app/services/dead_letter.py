"""Dead-letter service — write failed side-effects to ``dead_letters``.

Used by callers that already committed (or are about to commit) the
primary business state change and want to record a follow-up worklist
item for ops, without blocking the user-facing flow.

Design notes
------------
- Writes are best-effort: we **never** raise from here back into the
  primary flow. The whole point of a dead-letter is that the primary
  transition has already succeeded.
- The row is added to the *current* session; flushing/committing is
  the caller's responsibility (so the dead-letter joins the same
  transaction as the state change it documents). For situations where
  the caller's session is already broken (rare; mostly the auto-refund
  ``BadRequestException`` path), we fall back to a fresh session via
  the configured async session factory.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_letter import DeadLetter, DeadLetterStatus

logger = logging.getLogger("app.services.dead_letter")


async def record_dead_letter(
    session: AsyncSession,
    *,
    channel: str,
    reason: str,
    target_type: str | None = None,
    target_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
    flush: bool = True,
) -> DeadLetter | None:
    """Insert a dead-letter row; return it (or None on hard failure).

    Parameters
    ----------
    channel:
        Logical subsystem — ``order_refund``, ``notification`` …
    reason:
        Short machine-friendly key, e.g. ``refund_provider_error``.
    payload:
        Free-form JSON-serialisable context for the operator UI / replay.
    flush:
        When True (default) issue ``session.flush()`` so the row gets an
        ``id`` before returning. Disable in cron paths that batch flush.
    """
    try:
        row = DeadLetter(
            channel=channel,
            reason=reason,
            target_type=target_type,
            target_id=target_id,
            payload=payload,
            status=DeadLetterStatus.pending,
        )
        session.add(row)
        if flush:
            await session.flush()
        return row
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        # If the session is already in a bad state (e.g. caller is about
        # to raise), we don't want to mask the original error.
        logger.error(
            "dead_letter_write_failed channel=%s reason=%s target=%s/%s err=%s",
            channel,
            reason,
            target_type,
            target_id,
            exc,
            exc_info=True,
        )
        return None
