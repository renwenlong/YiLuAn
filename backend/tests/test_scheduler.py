"""Tests for backend scheduler (APScheduler-based expired order scanner).

D-018: 验证定时任务可正确扫描过期订单、无过期订单场景、异常容错，
以及 Redis 分布式锁在多副本场景下的去重语义。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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
# 1. 正常扫描：应取消过期订单
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

    # 打补丁：让 scheduler 使用测试用的 session factory
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

    failing_service = AsyncMock()
    failing_service.check_expired_orders.side_effect = RuntimeError("db boom")

    class _FailingServiceCls:
        def __init__(self, session):
            pass

        async def check_expired_orders(self):
            raise RuntimeError("db boom")

    # patch OrderService 为会抛错的版本
    with patch(
        "app.services.order.OrderService",
        _FailingServiceCls,
    ):
        result = await scan_expired_orders_job(app=_app_with_redis(_LockRedis()))

    assert result["status"] == "error"
    assert result["cancelled"] == 0


# ---------------------------------------------------------------------------
# 4. 分布式锁：第二次调用在锁未释放时应跳过
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_scan_expired_orders_skips_when_lock_held():
    redis_obj = _LockRedis()
    # 预先占位
    await redis_obj.set(EXPIRED_ORDER_LOCK_KEY, "1", nx=True, ex=EXPIRED_ORDER_LOCK_TTL_SECONDS)

    result = await scan_expired_orders_job(app=_app_with_redis(redis_obj))
    assert result["status"] == "skipped"
    assert result["cancelled"] == 0


# ---------------------------------------------------------------------------
# 5. 锁辅助函数：Redis 异常时退化为允许执行
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
