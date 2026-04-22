"""Tests for log retention cleanup jobs (D-027)."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_callback_log import PaymentCallbackLog
from app.models.sms_send_log import SmsSendLog
from app.tasks.log_retention import (
    cleanup_payment_callback_log,
    cleanup_sms_send_log,
)
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _now():
    return datetime.now(timezone.utc)


def _make_payment_log(*, created_at=None, expires_at=None):
    return PaymentCallbackLog(
        id=uuid.uuid4(),
        provider="mock",
        transaction_id=str(uuid.uuid4()),
        callback_type="pay",
        status="processed",
        created_at=created_at or _now(),
        expires_at=expires_at,
    )


def _make_sms_log(*, created_at=None, expires_at=None):
    return SmsSendLog(
        provider="mock",
        phone_masked="138****1234",
        phone_hash="a" * 64,
        template_code="SMS_OTP",
        status="success",
        created_at=created_at or _now(),
        expires_at=expires_at,
    )


async def _seed_and_run(records, cleanup_fn, **kwargs):
    """Insert records via test session, then run cleanup with patched async_session."""
    async with test_session_factory() as session:
        session.add_all(records)
        await session.commit()

    # Patch async_session in the log_retention module to use test DB
    with patch("app.tasks.log_retention.async_session", test_session_factory):
        result = await cleanup_fn(**kwargs)

    return result


async def _count(model):
    async with test_session_factory() as session:
        return (await session.execute(
            select(func.count()).select_from(model)
        )).scalar()


# ---------------------------------------------------------------------------
# Payment callback log cleanup
# ---------------------------------------------------------------------------
class TestCleanupPaymentCallbackLog:
    async def test_deletes_expired_records(self):
        """Records with expires_at in the past should be deleted."""
        result = await _seed_and_run(
            [
                _make_payment_log(expires_at=_now() - timedelta(days=1)),
                _make_payment_log(expires_at=_now() + timedelta(days=30)),
            ],
            cleanup_payment_callback_log,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 1
        assert await _count(PaymentCallbackLog) == 1

    async def test_keeps_unexpired_records(self):
        """Records with future expires_at should be kept."""
        result = await _seed_and_run(
            [_make_payment_log(expires_at=_now() + timedelta(days=60))],
            cleanup_payment_callback_log,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 0

    async def test_fallback_deletes_null_expires_old_created(self):
        """Historical records (expires_at=NULL) older than retention are deleted."""
        result = await _seed_and_run(
            [
                _make_payment_log(created_at=_now() - timedelta(days=100), expires_at=None),
                _make_payment_log(created_at=_now() - timedelta(days=10), expires_at=None),
            ],
            cleanup_payment_callback_log,
            retention_days=90,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 1


# ---------------------------------------------------------------------------
# SMS send log cleanup
# ---------------------------------------------------------------------------
class TestCleanupSmsSendLog:
    async def test_deletes_expired_records(self):
        """Records with expires_at in the past should be deleted."""
        result = await _seed_and_run(
            [
                _make_sms_log(expires_at=_now() - timedelta(hours=1)),
                _make_sms_log(expires_at=_now() + timedelta(days=30)),
            ],
            cleanup_sms_send_log,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 1
        assert await _count(SmsSendLog) == 1

    async def test_keeps_unexpired_records(self):
        """Records with future expires_at should be kept."""
        result = await _seed_and_run(
            [_make_sms_log(expires_at=_now() + timedelta(days=60))],
            cleanup_sms_send_log,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 0

    async def test_fallback_deletes_null_expires_old_created(self):
        """Historical SMS records (expires_at=NULL) older than retention are deleted."""
        result = await _seed_and_run(
            [
                _make_sms_log(created_at=_now() - timedelta(days=100), expires_at=None),
                _make_sms_log(created_at=_now() - timedelta(days=10), expires_at=None),
            ],
            cleanup_sms_send_log,
            retention_days=90,
        )
        assert result["status"] == "ok"
        assert result["deleted"] == 1


# ---------------------------------------------------------------------------
# Advisory lock behavior
# ---------------------------------------------------------------------------
class TestLockBehavior:
    async def test_payment_cleanup_skips_when_lock_held(self):
        """When lock cannot be acquired, job should return skipped."""
        # Seed an expired record
        async with test_session_factory() as session:
            session.add(_make_payment_log(expires_at=_now() - timedelta(days=1)))
            await session.commit()

        mock_lock = AsyncMock()
        mock_lock.acquired = False
        mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
        mock_lock.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.log_retention.async_session", test_session_factory), \
             patch("app.tasks.log_retention.acquire_scheduler_lock", return_value=mock_lock):
            result = await cleanup_payment_callback_log()

        assert result["status"] == "skipped"
        assert result["deleted"] == 0
        # Record should still exist
        assert await _count(PaymentCallbackLog) == 1

    async def test_sms_cleanup_skips_when_lock_held(self):
        """When lock cannot be acquired for SMS cleanup, job should skip."""
        async with test_session_factory() as session:
            session.add(_make_sms_log(expires_at=_now() - timedelta(days=1)))
            await session.commit()

        mock_lock = AsyncMock()
        mock_lock.acquired = False
        mock_lock.__aenter__ = AsyncMock(return_value=mock_lock)
        mock_lock.__aexit__ = AsyncMock(return_value=False)

        with patch("app.tasks.log_retention.async_session", test_session_factory), \
             patch("app.tasks.log_retention.acquire_scheduler_lock", return_value=mock_lock):
            result = await cleanup_sms_send_log()

        assert result["status"] == "skipped"
        assert result["deleted"] == 0
        assert await _count(SmsSendLog) == 1
