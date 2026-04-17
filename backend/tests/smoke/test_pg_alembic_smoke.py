"""PG + Alembic smoke tests.

Goal: 防止 model/alembic 脱钩。对真 PG 跑 `alembic upgrade head`，再验关键 CRUD +
enum 范围。未来谁改 model 没加迁移，此 smoke 立刻红。

运行方式:
    # 需要 PG 可用（docker compose up -d db 或 CI services: postgres）
    # 通过 SMOKE_DATABASE_URL 环境变量指定（asyncpg scheme）
    pytest -m smoke -q

默认 `pytest` 不收集 smoke（pyproject.toml: addopts = "-m 'not smoke'"）。
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

pytestmark = pytest.mark.smoke


BACKEND_DIR = Path(__file__).resolve().parents[2]


def _resolve_pg_url() -> str:
    """解析测试 PG URL。

    优先 SMOKE_DATABASE_URL；否则回退 docker-compose 默认（localhost:5432）。
    必须是 asyncpg scheme（alembic env.py 期望 async）。
    """
    url = os.environ.get("SMOKE_DATABASE_URL")
    if not url:
        # Also accept DATABASE_URL if set
        url = os.environ.get("DATABASE_URL")
    if not url:
        url = "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan"
    # normalise to asyncpg for runtime; alembic env reads settings.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


PG_URL = _resolve_pg_url()


def _sync_url(async_url: str) -> str:
    return async_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@pytest.fixture(scope="module", autouse=True)
def _alembic_upgrade_head():
    """对真 PG 跑 alembic upgrade head，确保 schema 最新。"""
    env = os.environ.copy()
    # alembic env.py 通过 settings.database_url 读取，支持 DATABASE_URL env 覆盖
    env["DATABASE_URL"] = PG_URL
    # 先降到 base 再 upgrade 会破坏现有数据；这里只做 upgrade head（幂等）
    # 如果数据库干净，upgrade head 会从头建表；如果已同步，是 no-op
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        pytest.fail(
            f"alembic upgrade head failed (rc={result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
    yield


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="module")
async def engine():
    eng = create_async_engine(PG_URL, echo=False)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session(engine) -> AsyncSession:
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()  # 保持 smoke 幂等，不污染 PG


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alembic_upgrade_head_no_error():
    """alembic upgrade head 已在 module 级 autouse fixture 执行成功。
    这里显式再验证一次 current revision 非空。"""
    eng = create_async_engine(PG_URL, echo=False)
    try:
        async with eng.connect() as conn:
            result = await conn.execute(text("SELECT version_num FROM alembic_version"))
            rows = result.all()
            assert len(rows) >= 1, "alembic_version table empty"
            assert rows[0][0], "version_num is empty"
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_order_status_enum_has_9_values():
    """校验 orderstatus enum 共 9 个值，且包含 rejected_by_companion + expired。"""
    expected = {
        "created",
        "accepted",
        "in_progress",
        "completed",
        "reviewed",
        "cancelled_by_patient",
        "cancelled_by_companion",
        "rejected_by_companion",
        "expired",
    }
    eng = create_async_engine(PG_URL, echo=False)
    try:
        async with eng.connect() as conn:
            result = await conn.execute(text("SELECT unnest(enum_range(NULL::orderstatus))"))
            values = {row[0] for row in result.all()}
        assert values == expected, f"enum mismatch. got={values} expected={expected}"
        assert len(values) == 9
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_payments_has_wechat_columns():
    """校验 payments 表含 trade_no / prepay_id / refund_id / callback_raw 四列。"""
    eng = create_async_engine(PG_URL, echo=False)
    try:
        async with eng.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name='payments'
                    """
                )
            )
            cols = {row[0] for row in result.all()}
        for required in ("trade_no", "prepay_id", "refund_id", "callback_raw"):
            assert required in cols, f"payments table missing column: {required}"
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_crud_user_order_payment_roundtrip():
    """端到端 CRUD：user → hospital → order(rejected) → order(expired) → payment(全 wechat 列)。

    所有插入用唯一 UUID/phone，最终 rollback 不污染数据（module-scoped engine）。
    """
    from app.models.hospital import Hospital
    from app.models.order import Order, OrderStatus, ServiceType
    from app.models.payment import Payment
    from app.models.user import User, UserRole

    eng = create_async_engine(PG_URL, echo=False)
    try:
        maker = async_sessionmaker(eng, expire_on_commit=False)
        async with maker() as s:
            # 1. user
            u = User(
                phone=f"139{uuid.uuid4().int % 100000000:08d}",
                role=UserRole.patient,
                roles="patient",
                display_name="smoke-test-user",
            )
            s.add(u)
            await s.flush()
            assert u.id is not None

            # 2. hospital
            h = Hospital(name=f"smoke-hospital-{uuid.uuid4().hex[:8]}")
            s.add(h)
            await s.flush()

            # 3. order with status=rejected_by_companion
            o_rej = Order(
                order_number=f"SMOKE-REJ-{uuid.uuid4().hex[:12]}",
                patient_id=u.id,
                hospital_id=h.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.rejected_by_companion,
                appointment_date="2026-05-01",
                appointment_time="09:00",
                price=299.0,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
            s.add(o_rej)
            await s.flush()
            assert o_rej.status == OrderStatus.rejected_by_companion

            # 4. order with status=expired
            o_exp = Order(
                order_number=f"SMOKE-EXP-{uuid.uuid4().hex[:12]}",
                patient_id=u.id,
                hospital_id=h.id,
                service_type=ServiceType.half_accompany,
                status=OrderStatus.expired,
                appointment_date="2026-05-01",
                appointment_time="10:00",
                price=199.0,
            )
            s.add(o_exp)
            await s.flush()
            assert o_exp.status == OrderStatus.expired

            # 5. payment 含全部 wechat 列
            p = Payment(
                order_id=o_rej.id,
                user_id=u.id,
                amount=299.0,
                payment_type="pay",
                status="success",
                trade_no=f"smoke-trade-{uuid.uuid4().hex[:16]}",
                prepay_id=f"wx-prepay-{uuid.uuid4().hex[:24]}",
                refund_id=None,
                callback_raw='{"mock":"callback"}',
            )
            s.add(p)
            await s.flush()
            assert p.trade_no is not None
            assert p.prepay_id is not None
            assert p.callback_raw is not None

            # 6. readback via SQL 校验
            result = await s.execute(
                text("SELECT status::text FROM orders WHERE id = :oid"),
                {"oid": o_rej.id},
            )
            assert result.scalar_one() == "rejected_by_companion"

            result = await s.execute(
                text("SELECT status::text FROM orders WHERE id = :oid"),
                {"oid": o_exp.id},
            )
            assert result.scalar_one() == "expired"

            # 7. rollback 清理（不污染 PG）
            await s.rollback()
    finally:
        await eng.dispose()


@pytest.mark.asyncio
async def test_alembic_check_no_drift():
    """`alembic check` 应无 diff（model 与 migration 已同步）。

    alembic >= 1.9 支持 `check` 子命令。若当前 alembic 版本不支持，则跳过。
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = PG_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=str(BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        # alembic check 在有 drift 时退出码非 0，打印详情便于排查
        combined = (result.stdout or "") + (result.stderr or "")
        # 若是 alembic 版本过老，skip
        if "No such command" in combined or "invalid choice" in combined:
            pytest.skip(f"alembic check not supported in this alembic version: {combined}")
        pytest.fail(
            f"alembic check detected drift (rc={result.returncode})\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
