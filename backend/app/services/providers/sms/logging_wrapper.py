"""SMS send-log wrapper (A21-02b / D-033).

Wraps any concrete SMSProvider so that every send_otp / send_notification call
auto-persists a row to the sms_send_log table. Provider implementations are
unchanged; the outbound decorator semantics (A5/A21-03) are preserved.

Write semantics:
- INSERT status='pending' -> call inner.send_xxx ->
  - on result.ok=True: UPDATE status='success' + biz_id + response_code/msg
  - on result.ok=False: UPDATE status='failed' + response code/msg, no raise
  - on exception: UPDATE status='failed' + record exception repr, then re-raise

Storage safety:
- OTP plaintext NEVER stored (no params column).
- phone is split into masked (138******34, app.core.pii.mask_phone) +
  hash (sha256 with salt, app.core.pii.hash_phone).
- expires_at = now() + 90d (matches D-027 / payment_callback_log convention).

DB session source:
- Uses app.database.async_session, opened as a short transaction independent
  of any business transaction. This means logs survive business rollbacks --
  audit-wise this is desired ("send was attempted").
- Tests inject a SQLite in-memory factory by monkeypatching
  app.database.async_session.

Failure modes:
- DB write failures must NEVER break the SMS send path. All writes are
  wrapped in try/except + logger.exception. The log table is best-effort.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import update

from app import database as _database
from app.config import settings
from app.core.pii import hash_phone, mask_phone
from app.services.providers.sms.base import SMSProvider, SMSResult

logger = logging.getLogger(__name__)


# 90-day TTL (matches D-027 / payment_callback_log).
LOG_TTL = timedelta(days=90)


class LoggingSMSProviderWrapper(SMSProvider):
    """Wrap a concrete SMSProvider, persisting one row per send."""

    def __init__(self, inner: SMSProvider) -> None:
        self._inner = inner
        # Forward `name` so introspection (provider.name) keeps working.
        self.name = getattr(inner, "name", "unknown")

    # ----------------------------------------------------------------- API

    async def send_otp(
        self,
        phone: str,
        code: str,
        template_id: str | None = None,
        *,
        user_id: UUID | None = None,
    ) -> SMSResult:
        template_code = (
            template_id
            or getattr(settings, "sms_template_code", "")
            or "OTP"
        )
        return await self._send_with_log(
            method="send_otp",
            phone=phone,
            template_code=template_code,
            user_id=user_id,
            kwargs={"code": code, "template_id": template_id},
        )

    async def send_notification(
        self,
        phone: str,
        template_id: str,
        params: dict[str, Any] | None = None,
        *,
        user_id: UUID | None = None,
    ) -> SMSResult:
        return await self._send_with_log(
            method="send_notification",
            phone=phone,
            template_code=template_id,
            user_id=user_id,
            kwargs={"template_id": template_id, "params": params},
        )

    # ------------------------------------------------------------- internal

    async def _send_with_log(
        self,
        *,
        method: str,
        phone: str,
        template_code: str,
        user_id: UUID | None,
        kwargs: dict[str, Any],
    ) -> SMSResult:
        log_id = await self._insert_pending(
            phone=phone,
            template_code=template_code,
            user_id=user_id,
        )

        # Drop None template_id so we don't pass an unwanted kwarg.
        call_kwargs = {
            k: v for k, v in kwargs.items() if v is not None or k == "params"
        }

        try:
            inner_method = getattr(self._inner, method)
            result: SMSResult = await inner_method(phone, **call_kwargs)
        except Exception as exc:  # noqa: BLE001 -- log then re-raise
            await self._update_failed(
                log_id,
                response_code=type(exc).__name__,
                response_msg=str(exc)[:512],
            )
            raise

        if result.ok:
            biz_id = None
            if isinstance(result.extra, dict):
                biz_id = (
                    result.extra.get("biz_id") or result.extra.get("BizId")
                )
            await self._update_success(
                log_id,
                biz_id=biz_id,
                response_code=result.code,
                response_msg=(result.message or "")[:512] or None,
            )
        else:
            await self._update_failed(
                log_id,
                response_code=result.code,
                response_msg=(result.message or "")[:512] or None,
            )
        return result

    async def _insert_pending(
        self,
        *,
        phone: str,
        template_code: str,
        user_id: UUID | None,
    ) -> int | None:
        # Resolve session factory lazily so tests can monkeypatch
        # app.database.async_session to an in-memory factory.
        from app.models.sms_send_log import SmsSendLog

        salt = getattr(
            settings, "pii_hash_salt", "yiluan-dev-salt-do-not-use-in-prod"
        )
        now = datetime.now(timezone.utc)
        row = SmsSendLog(
            provider=getattr(self._inner, "name", "unknown"),
            phone_masked=mask_phone(phone),
            phone_hash=hash_phone(phone, salt),
            template_code=template_code,
            sign_name=getattr(settings, "sms_sign_name", "") or None,
            status="pending",
            user_id=user_id,
            created_at=now,
            expires_at=now + LOG_TTL,
        )
        try:
            async with _database.async_session() as session:
                session.add(row)
                await session.commit()
                await session.refresh(row)
                return row.id
        except Exception:  # noqa: BLE001
            logger.exception("[sms-log] failed to insert pending row")
            return None

    async def _update_success(
        self,
        log_id: int | None,
        *,
        biz_id: str | None,
        response_code: str | None,
        response_msg: str | None,
    ) -> None:
        await self._update_status(
            log_id,
            status="success",
            biz_id=biz_id,
            response_code=response_code,
            response_msg=response_msg,
        )

    async def _update_failed(
        self,
        log_id: int | None,
        *,
        response_code: str | None,
        response_msg: str | None,
    ) -> None:
        await self._update_status(
            log_id,
            status="failed",
            biz_id=None,
            response_code=response_code,
            response_msg=response_msg,
        )

    async def _update_status(
        self,
        log_id: int | None,
        *,
        status: str,
        biz_id: str | None,
        response_code: str | None,
        response_msg: str | None,
    ) -> None:
        if log_id is None:
            return
        from app.models.sms_send_log import SmsSendLog

        values: dict[str, Any] = {"status": status}
        if biz_id is not None:
            values["biz_id"] = biz_id
        if response_code is not None:
            values["response_code"] = response_code
        if response_msg is not None:
            values["response_msg"] = response_msg

        try:
            async with _database.async_session() as session:
                await session.execute(
                    update(SmsSendLog)
                    .where(SmsSendLog.id == log_id)
                    .values(**values)
                )
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception(
                "[sms-log] failed to update log_id=%s status=%s",
                log_id,
                status,
            )


def wrap_with_logging(provider: SMSProvider) -> SMSProvider:
    """Return provider wrapped so every send is persisted to sms_send_log.

    Idempotent: wrapping an already-wrapped provider returns it unchanged.
    """
    if isinstance(provider, LoggingSMSProviderWrapper):
        return provider
    return LoggingSMSProviderWrapper(provider)
