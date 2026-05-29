"""Tests for S2-DEV-006 — scheduler lock + token anomaly scanner + AI enqueue.

Acceptance #4/#5:
- 多副本并发 enqueue 只扣 1 次费 (process_pending_digests + scheduler lock)
- 滚动窗口边界：4 次/6 次 distinct, 同人复用不计 distinct, 24h 整点
- schedule-lock 2 副本并发抢锁
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.cron.ai_summary_enqueue import (
    enqueue_ai_digest,
    process_pending_digests_job,
)
from app.cron.share_token_scanner import scan_share_token_anomalies_job
from app.models.ai_digest import AIDigest, AIDigestStatus
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.order_share_token import OrderShareToken, ShareScope
from app.models.user import User, UserRole
from app.repositories.order_share_token import OrderShareTokenRepository
from app.core.distributed_lock import RedisNXLock
from tests.conftest import FakeRedis, test_session_factory


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


class _LockRedis(FakeRedis):
    """FakeRedis with SET NX semantics used by RedisNXLock + budget ops."""

    async def set(self, key, value, *, nx=False, ex=None, **kw):  # type: ignore[override]
        if nx and key in self._store:
            return None
        self._store[key] = str(value)
        return True

    async def incrbyfloat(self, key, amount):
        cur = float(self._store.get(key, "0"))
        new = cur + float(amount)
        self._store[key] = str(new)
        return new

    async def expire(self, key, ttl):
        return True

    async def delete(self, *keys):
        n = 0
        for k in keys:
            if k in self._store:
                del self._store[k]
                n += 1
        return n


class _FakeApp:
    def __init__(self, redis):
        self.state = type("S", (), {"redis": redis})()


@pytest.fixture(autouse=True)
def _patch_job_sessions():
    """Point both cron jobs' ``async_session`` at the SQLite test factory.

    The jobs create their own session (no request context); without this
    they'd hit the real Postgres DSN (absent in CI) and the PG advisory
    lock would report NOT-acquired → every job would skip.
    """
    with patch(
        "app.cron.ai_summary_enqueue.async_session", test_session_factory
    ), patch(
        "app.cron.share_token_scanner.async_session", test_session_factory
    ):
        yield


async def _seed_order(status=OrderStatus.completed) -> uuid.UUID:
    async with test_session_factory() as session:
        user = User(
            phone=f"139{uuid.uuid4().int % 100000000:08d}",
            role=UserRole.patient,
            roles="patient",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        hospital = Hospital(id=uuid.uuid4(), name="H1")
        session.add(hospital)
        await session.flush()
        order = Order(
            id=uuid.uuid4(),
            order_number=f"YLA-{uuid.uuid4().hex[:10].upper()}",
            patient_id=user.id,
            hospital_id=hospital.id,
            service_type=ServiceType.full_accompany,
            status=status,
            appointment_date="2026-06-01",
            appointment_time="09:00",
            price=Decimal("299.00"),
        )
        session.add(order)
        await session.commit()
        return order.id, user.id


async def _seed_token(order_id, created_by) -> OrderShareToken:
    async with test_session_factory() as session:
        token = await OrderShareTokenRepository(session).create_with_active_cap(
            order_id=order_id,
            created_by=created_by,
            order_completed_at=None,
            share_scope=ShareScope.FULL,
        )
        await session.commit()
        await session.refresh(token)
        return token


# ===========================================================================
# 1. enqueue idempotency
# ===========================================================================


@pytest.mark.asyncio
async def test_enqueue_is_idempotent_on_order_id():
    order_id, _ = await _seed_order()
    async with test_session_factory() as session:
        first = await enqueue_ai_digest(session, order_id)
        await session.commit()
    async with test_session_factory() as session:
        second = await enqueue_ai_digest(session, order_id)
        await session.commit()
    assert first is True
    assert second is False
    async with test_session_factory() as session:
        rows = (
            await session.execute(
                select(AIDigest).where(AIDigest.order_id == order_id)
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].status == AIDigestStatus.PENDING


# ===========================================================================
# 2. worker drains pending exactly once (charges once)
# ===========================================================================


@pytest.mark.asyncio
async def test_worker_processes_pending_and_charges_once():
    order_id, _ = await _seed_order()
    async with test_session_factory() as session:
        await enqueue_ai_digest(session, order_id)
        await session.commit()

    redis = _LockRedis()
    app = _FakeApp(redis)
    call_count = {"n": 0}

    async def _fake_generate(*, session, redis, order_id, prompt, **kw):
        call_count["n"] += 1
        from app.services.ai_summary.digester import _persist_and_metric

        return await _persist_and_metric(
            session=session,
            order_id=order_id,
            status=AIDigestStatus.OK,
            summary="ok",
            cost_yuan=Decimal("0.01"),
            model="deepseek-chat",
            degraded_reason=None,
        )

    with patch(
        "app.cron.ai_summary_enqueue.generate_digest", new=_fake_generate
    ):
        r1 = await process_pending_digests_job(app=app)
        # Second run: nothing pending → no extra charge.
        r2 = await process_pending_digests_job(app=app)

    assert r1["status"] == "ok" and r1["processed"] == 1
    assert r2["processed"] == 0
    assert call_count["n"] == 1, "digest must be generated exactly once"


# ===========================================================================
# 3. multi-replica: second replica skips (scheduler lock)
# ===========================================================================


@pytest.mark.asyncio
async def test_two_replicas_only_one_processes():
    order_id, _ = await _seed_order()
    async with test_session_factory() as session:
        await enqueue_ai_digest(session, order_id)
        await session.commit()

    # Shared redis → shared NX lock across "replicas".
    redis = _LockRedis()
    app = _FakeApp(redis)
    results = []

    async def _fake_generate(*, session, redis, order_id, prompt, **kw):
        from app.services.ai_summary.digester import _persist_and_metric

        return await _persist_and_metric(
            session=session,
            order_id=order_id,
            status=AIDigestStatus.OK,
            summary="ok",
            cost_yuan=Decimal("0.01"),
            model="deepseek-chat",
            degraded_reason=None,
        )

    # Pre-acquire the lock as if replica A holds it; replica B must skip.
    from app.cron.ai_summary_enqueue import AI_DIGEST_WORKER_LOCK_KEY

    await redis.set(AI_DIGEST_WORKER_LOCK_KEY, "1", nx=True, ex=55)
    with patch(
        "app.cron.ai_summary_enqueue.generate_digest", new=_fake_generate
    ):
        r = await process_pending_digests_job(app=app)
    assert r["status"] == "skipped"
    assert r["processed"] == 0


@pytest.mark.asyncio
async def test_redis_nx_lock_mutual_exclusion():
    """Two concurrent acquirers of the same RedisNXLock key: only one wins."""
    redis = _LockRedis()
    key = "yiluan:test:lock:contention"
    acquired_flags = []

    async def _try():
        lock = RedisNXLock(redis, key, 30)
        async with lock:
            acquired_flags.append(lock.acquired)
            # hold briefly so the second contender sees the key present
            import asyncio

            await asyncio.sleep(0.01)

    import asyncio

    await asyncio.gather(_try(), _try())
    # Exactly one True (winner) and one False (loser) — never two winners.
    assert acquired_flags.count(True) == 1
    assert acquired_flags.count(False) == 1


# ===========================================================================
# 4. rolling-window distinct count
# ===========================================================================


async def _log_access(token, openid, *, at):
    async with test_session_factory() as session:
        from app.models.order_share_access_log import OrderShareAccessLog

        session.add(
            OrderShareAccessLog(
                token_id=token.id,
                order_id=token.order_id,
                accessor_openid=openid,
                accessed_at=at,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_distinct_window_same_person_not_double_counted():
    order_id, uid = await _seed_order()
    token = await _seed_token(order_id, uid)
    now = datetime.now(timezone.utc)
    # Same openid 5 times within window → distinct == 1.
    for i in range(5):
        await _log_access(token, "wx-same", at=now - timedelta(minutes=i))
    async with test_session_factory() as session:
        n = await OrderShareTokenRepository(session).count_distinct_accessors_in_window(
            token.id, now=now
        )
    assert n == 1


@pytest.mark.asyncio
async def test_distinct_window_excludes_outside_24h():
    order_id, uid = await _seed_order()
    token = await _seed_token(order_id, uid)
    now = datetime.now(timezone.utc)
    # 3 inside, 3 outside the 24h window.
    for i in range(3):
        await _log_access(token, f"in-{i}", at=now - timedelta(hours=1))
    for i in range(3):
        await _log_access(token, f"out-{i}", at=now - timedelta(hours=25))
    async with test_session_factory() as session:
        n = await OrderShareTokenRepository(session).count_distinct_accessors_in_window(
            token.id, now=now
        )
    assert n == 3


@pytest.mark.asyncio
async def test_scanner_revokes_when_over_threshold():
    order_id, uid = await _seed_order()
    token = await _seed_token(order_id, uid)
    now = datetime.now(timezone.utc)
    # 6 distinct openids in 24h → > 5 threshold → revoke.
    for i in range(6):
        await _log_access(token, f"wx-{i}", at=now - timedelta(minutes=i))

    app = _FakeApp(_LockRedis())
    r = await scan_share_token_anomalies_job(app=app)
    assert r["status"] == "ok"
    assert r["revoked"] == 1

    async with test_session_factory() as session:
        row = await session.get(OrderShareToken, token.id)
        assert row.revoked_at is not None


@pytest.mark.asyncio
async def test_scanner_does_not_revoke_at_threshold_boundary():
    order_id, uid = await _seed_order()
    token = await _seed_token(order_id, uid)
    now = datetime.now(timezone.utc)
    # Exactly 5 distinct → NOT > 5 → keep.
    for i in range(5):
        await _log_access(token, f"wx-{i}", at=now - timedelta(minutes=i))

    app = _FakeApp(_LockRedis())
    r = await scan_share_token_anomalies_job(app=app)
    assert r["revoked"] == 0
    async with test_session_factory() as session:
        row = await session.get(OrderShareToken, token.id)
        assert row.revoked_at is None
