"""Tests for backend scheduler (APScheduler-based expired order scanner).

D-018: 验证定时任务可正确扫描过期订单、无过期订单场景、异常容错，
以及分布式锁（Redis NX + PG advisory）在多副本场景下的去重语义。

2026-04-17 升级后，生产使用 PG advisory lock；SQLite 测试环境自动退化为 Redis NX
锁（best-effort），两条路径均被覆盖。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.distributed_lock import (
    PostgresAdvisoryLock,
    RedisNXLock,
    acquire_scheduler_lock,
    lock_key_to_bigint,
)
from app.models.order import OrderStatus, ServiceType
from app.models.user import UserRole
from app.tasks.scheduler import (
    EXPIRED_ORDER_LOCK_KEY,
    EXPIRED_ORDER_LOCK_TTL_SECONDS,
    _try_acquire_lock,
    create_scheduler,
    scan_expired_orders_job,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
class _LockRedis:
    """最小可信 Redis mock，支持 set(nx=True, ex=...)."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.calls: list[tuple] = []

    async def set(self, key, value, nx=False, ex=None):
        self.calls.append((key, value, nx, ex))
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True


def _app_with_redis(redis_obj):
    return SimpleNamespace(state=SimpleNamespace(redis=redis_obj))


# ---------------------------------------------------------------------------
# 1. 正常扫描：应取消过期订单（SQLite → RedisNXLock 路径）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_cancels_expired(
    seed_user, seed_hospital, seed_order
):
    patient = await seed_user(phone="13811110001", role=UserRole.patient)
    hospital = await seed_hospital(name="过期订单测试医院")
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        status=OrderStatus.created,
        service_type=ServiceType.full_accompany,
        expires_at=past,
    )

    from app.tasks import scheduler as scheduler_mod
    from tests.conftest import test_session_factory

    with patch.object(scheduler_mod, "async_session", test_session_factory):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "ok"
    assert result["cancelled"] == 1


# ---------------------------------------------------------------------------
# 2. 无过期订单：正常返回 0
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_no_expired(
    seed_user, seed_hospital, seed_order
):
    patient = await seed_user(phone="13811110002", role=UserRole.patient)
    hospital = await seed_hospital(name="未过期订单测试医院")
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        status=OrderStatus.created,
        expires_at=future,
    )

    from app.tasks import scheduler as scheduler_mod
    from tests.conftest import test_session_factory

    with patch.object(scheduler_mod, "async_session", test_session_factory):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "ok"
    assert result["cancelled"] == 0


# ---------------------------------------------------------------------------
# 3. 异常处理：OrderService 抛异常不应击穿调度器
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_handles_exception():
    from app.tasks import scheduler as scheduler_mod
    from tests.conftest import test_session_factory

    class _FailingServiceCls:
        def __init__(self, session):
            pass

        async def check_expired_orders(self):
            raise RuntimeError("db boom")

    # patch OrderService 为会抛错的版本 + 指向测试 session factory
    with patch.object(scheduler_mod, "async_session", test_session_factory), patch(
        "app.services.order.OrderService",
        _FailingServiceCls,
    ):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "error"
    assert result["cancelled"] == 0


# ---------------------------------------------------------------------------
# 4. Redis 锁：锁未释放时第二次调用应跳过（SQLite 路径）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_skips_when_redis_lock_held():
    from app.tasks import scheduler as scheduler_mod
    from tests.conftest import test_session_factory

    redis_obj = _LockRedis()
    # 预先占位
    await redis_obj.set(EXPIRED_ORDER_LOCK_KEY, "1", nx=True, ex=EXPIRED_ORDER_LOCK_TTL_SECONDS)

    with patch.object(scheduler_mod, "async_session", test_session_factory):
        result = await scan_expired_orders_job(app=_app_with_redis(redis_obj))
    assert result["status"] == "skipped"
    assert result["cancelled"] == 0


# ---------------------------------------------------------------------------
# 5. 旧 helper：Redis 异常时退化为允许执行（向后兼容）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_try_acquire_lock_redis_none():
    assert await _try_acquire_lock(None, "k", 10) is True


@pytest.mark.asyncio
async def test_try_acquire_lock_redis_exception():
    class _BrokenRedis:
        async def set(self, *args, **kwargs):
            raise RuntimeError("redis down")

    assert await _try_acquire_lock(_BrokenRedis(), "k", 10) is True


# ---------------------------------------------------------------------------
# 6. 调度器构造：任务已注册且配置正确
# ---------------------------------------------------------------------------
def test_create_scheduler_registers_expired_order_job():
    app = _app_with_redis(None)
    scheduler = create_scheduler(app)
    try:
        jobs = scheduler.get_jobs()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == "scan_expired_orders"
        assert job.max_instances == 1
        assert job.coalesce is True
    finally:
        # 不 start，避免事件循环绑定问题；直接清理
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass


# ===========================================================================
# D-018 升级：分布式锁生产级（PG advisory + Redis NX 回退）
# ===========================================================================

# ---------------------------------------------------------------------------
# 7. lock_key_to_bigint：稳定 + 区分不同 key
# ---------------------------------------------------------------------------
def test_lock_key_to_bigint_stable_and_distinct():
    a1 = lock_key_to_bigint("yiluan:scheduler:expired-orders:lock")
    a2 = lock_key_to_bigint("yiluan:scheduler:expired-orders:lock")
    b = lock_key_to_bigint("yiluan:scheduler:another-job:lock")
    assert a1 == a2
    assert a1 != b
    # 必须落在 signed int64 范围
    assert -(2**63) <= a1 < 2**63
    assert -(2**63) <= b < 2**63


# ---------------------------------------------------------------------------
# 8. PostgresAdvisoryLock：成功获取并释放
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_postgres_advisory_lock_acquires_and_releases():
    executed: list[str] = []

    class _Result:
        def __init__(self, value):
            self._v = value

        def scalar(self):
            return self._v

    async def _execute(stmt, params=None):
        sql = str(stmt).lower()
        executed.append(sql)
        if "pg_try_advisory_lock" in sql:
            return _Result(True)
        if "pg_advisory_unlock" in sql:
            return _Result(True)
        return _Result(None)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)

    lock = PostgresAdvisoryLock(session, "yiluan:test:key-a")
    async with lock:
        assert lock.acquired is True

    assert any("pg_try_advisory_lock" in s for s in executed)
    assert any("pg_advisory_unlock" in s for s in executed)


# ---------------------------------------------------------------------------
# 9. PostgresAdvisoryLock：被其他实例持有 → 跳过
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_postgres_advisory_lock_skip_when_held():
    class _Result:
        def scalar(self):
            return False  # 其他实例持有

    session = MagicMock()
    session.execute = AsyncMock(return_value=_Result())

    lock = PostgresAdvisoryLock(session, "yiluan:test:key-b")
    async with lock:
        assert lock.acquired is False

    # 未获取锁时不应尝试 unlock（调用次数应为 1）
    assert session.execute.await_count == 1


# ---------------------------------------------------------------------------
# 10. PostgresAdvisoryLock：异常时安全降级为"未获取"
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_postgres_advisory_lock_exception_treated_as_not_acquired():
    session = MagicMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db boom"))

    lock = PostgresAdvisoryLock(session, "yiluan:test:key-c")
    async with lock:
        assert lock.acquired is False
    # 不应调用 unlock
    assert session.execute.await_count == 1


# ---------------------------------------------------------------------------
# 11. PostgresAdvisoryLock：即便业务代码抛异常也会 unlock
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_postgres_advisory_lock_releases_on_business_exception():
    class _Result:
        def __init__(self, v):
            self._v = v

        def scalar(self):
            return self._v

    calls: list[str] = []

    async def _execute(stmt, params=None):
        sql = str(stmt).lower()
        calls.append(sql)
        if "pg_try_advisory_lock" in sql:
            return _Result(True)
        return _Result(True)

    session = MagicMock()
    session.execute = AsyncMock(side_effect=_execute)

    lock = PostgresAdvisoryLock(session, "yiluan:test:key-d")
    with pytest.raises(RuntimeError):
        async with lock:
            assert lock.acquired is True
            raise RuntimeError("work failed")

    # 必须执行了 unlock
    assert any("pg_advisory_unlock" in s for s in calls)


# ---------------------------------------------------------------------------
# 12. RedisNXLock：成功获取 / 被他人持有 / Redis 不可用退化
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_redis_nx_lock_acquires():
    redis = _LockRedis()
    lock = RedisNXLock(redis, "k", 30)
    async with lock:
        assert lock.acquired is True


@pytest.mark.asyncio
async def test_redis_nx_lock_skips_when_held():
    redis = _LockRedis()
    await redis.set("k", "1", nx=True, ex=30)
    lock = RedisNXLock(redis, "k", 30)
    async with lock:
        assert lock.acquired is False


@pytest.mark.asyncio
async def test_redis_nx_lock_none_redis_fallback():
    lock = RedisNXLock(None, "k", 30)
    async with lock:
        # Redis 不可用时退化为允许执行（与历史 best-effort 一致）
        assert lock.acquired is True


@pytest.mark.asyncio
async def test_redis_nx_lock_redis_exception_fallback():
    class _Broken:
        async def set(self, *a, **kw):
            raise RuntimeError("redis down")

    lock = RedisNXLock(_Broken(), "k", 30)
    async with lock:
        assert lock.acquired is True


# ---------------------------------------------------------------------------
# 13. 工厂：按方言选择锁实现
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_acquire_scheduler_lock_uses_pg_for_postgresql():
    session = MagicMock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    lock = acquire_scheduler_lock(
        session=session, redis_client=_LockRedis(), key="k", ttl=30
    )
    assert isinstance(lock, PostgresAdvisoryLock)


@pytest.mark.asyncio
async def test_acquire_scheduler_lock_uses_redis_for_sqlite():
    session = MagicMock()
    session.get_bind.return_value = SimpleNamespace(dialect=SimpleNamespace(name="sqlite"))
    redis = _LockRedis()
    lock = acquire_scheduler_lock(
        session=session, redis_client=redis, key="k", ttl=30
    )
    assert isinstance(lock, RedisNXLock)


@pytest.mark.asyncio
async def test_acquire_scheduler_lock_falls_back_when_no_session():
    lock = acquire_scheduler_lock(
        session=None, redis_client=_LockRedis(), key="k", ttl=30
    )
    assert isinstance(lock, RedisNXLock)


# ---------------------------------------------------------------------------
# 14. 端到端：scheduler_job 在 PG 方言下走 advisory lock 路径（模拟）
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_uses_pg_advisory_when_postgres(
    seed_user, seed_hospital, seed_order
):
    """模拟生产 PG 环境：patch dialect name 为 postgresql，
    并拦截 pg_try_advisory_lock 返回 True，验证走 PG 锁路径。
    """
    patient = await seed_user(phone="13811110003", role=UserRole.patient)
    hospital = await seed_hospital(name="PG 锁测试医院")
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    await seed_order(
        patient_id=patient.id,
        hospital_id=hospital.id,
        status=OrderStatus.created,
        expires_at=past,
    )

    from app.tasks import scheduler as scheduler_mod
    from app.core import distributed_lock as lock_mod
    from tests.conftest import test_session_factory

    # 让 dialect 被识别为 postgresql
    orig_dialect = lock_mod._session_dialect

    def fake_dialect(session):
        return "postgresql"

    pg_calls: list[str] = []
    orig_execute = None

    async def _patched_execute(self, stmt, params=None):
        sql = str(stmt).lower()
        if "pg_try_advisory_lock" in sql:
            pg_calls.append("lock")
            class _R:
                def scalar(self):
                    return True
            return _R()
        if "pg_advisory_unlock" in sql:
            pg_calls.append("unlock")
            class _R:
                def scalar(self):
                    return True
            return _R()
        return await orig_execute(self, stmt, params)

    from sqlalchemy.ext.asyncio import AsyncSession as _AS
    orig_execute = _AS.execute

    with patch.object(scheduler_mod, "async_session", test_session_factory), patch.object(
        lock_mod, "_session_dialect", fake_dialect
    ), patch.object(_AS, "execute", _patched_execute):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "ok"
    assert result["cancelled"] == 1
    assert "lock" in pg_calls
    assert "unlock" in pg_calls


@pytest.mark.asyncio
async def test_scan_expired_orders_skipped_when_pg_lock_held(
    seed_user, seed_hospital, seed_order
):
    """PG 方言 + pg_try_advisory_lock 返回 False → 应跳过本轮。"""
    from app.tasks import scheduler as scheduler_mod
    from app.core import distributed_lock as lock_mod
    from tests.conftest import test_session_factory

    def fake_dialect(session):
        return "postgresql"

    from sqlalchemy.ext.asyncio import AsyncSession as _AS
    orig_execute = _AS.execute

    async def _patched_execute(self, stmt, params=None):
        sql = str(stmt).lower()
        if "pg_try_advisory_lock" in sql:
            class _R:
                def scalar(self):
                    return False  # 其他实例持有
            return _R()
        if "pg_advisory_unlock" in sql:
            class _R:
                def scalar(self):
                    return True
            return _R()
        return await orig_execute(self, stmt, params)

    with patch.object(scheduler_mod, "async_session", test_session_factory), patch.object(
        lock_mod, "_session_dialect", fake_dialect
    ), patch.object(_AS, "execute", _patched_execute):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "skipped"
    assert result["cancelled"] == 0
