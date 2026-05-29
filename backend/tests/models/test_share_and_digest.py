"""Tests for OrderShareToken + AIDigest models and the
OrderShareTokenRepository (ADR-0036 §2.3, PRD-001 v1.2 §4).

Acceptance covered:
- token UNIQUE + indexes (导入即生效, 见 test_models_import_smoke)
- alembic upgrade/downgrade dry-run (test_alembic_round_trip)
- per-order active-token cap = 3 via repo helper (auto-revoke oldest)
- expires_at default = order.completed_at + 24h, hard cap = created_at + 7d
- ShareScope enum default = full, can switch to progress_only
- revoke 后 is_active == False
- record_access 聚合 first/distinct/last
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import (
    AIDigest,
    AIDigestStatus,
    OrderShareToken,
    ShareScope,
    compute_expires_at,
    generate_token,
)
from app.repositories.order_share_token import OrderShareTokenRepository
from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# pure helpers — no DB
# ---------------------------------------------------------------------------


def test_generate_token_is_unique_and_url_safe():
    seen = {generate_token() for _ in range(200)}
    assert len(seen) == 200
    for tok in list(seen)[:10]:
        assert len(tok) == 32
        # URL-safe alphabet (token_urlsafe) is base64url subset.
        assert all(c.isalnum() or c in "-_" for c in tok)


def test_compute_expires_at_pre_completion_uses_24h_default():
    created = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    exp = compute_expires_at(created_at=created, order_completed_at=None)
    assert exp == created + timedelta(hours=24)


def test_compute_expires_at_post_completion_uses_completed_at_plus_24h():
    created = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    completed = created + timedelta(hours=4)
    exp = compute_expires_at(
        created_at=created, order_completed_at=completed
    )
    assert exp == completed + timedelta(hours=24)


def test_compute_expires_at_hard_cap_7d():
    created = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    # Completed late — 8 days after share creation — must clamp.
    completed = created + timedelta(days=8)
    exp = compute_expires_at(
        created_at=created, order_completed_at=completed
    )
    assert exp == created + timedelta(days=7)


# ---------------------------------------------------------------------------
# alembic round-trip dry-run (sqlite memory)
# ---------------------------------------------------------------------------


def test_alembic_round_trip_upgrade_then_downgrade():
    """sqlite in-memory: upgrade to a1b2c3d4e5f6 then downgrade.

    We don't run the full project alembic config (it points at the real
    postgres in CI); instead we exercise the migration ops directly so a
    syntax/typo regression in the new revision is still caught.
    """
    from alembic.runtime.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import create_engine

    eng = create_engine("sqlite:///:memory:")
    with eng.begin() as conn:
        ctx = MigrationContext.configure(conn)
        op = Operations(ctx)

        # Minimal stubs for FK targets so create_table won't fail.
        import sqlalchemy as sa

        op.create_table(
            "orders",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        )
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        )

        # Inline the migration logic against this Operations instance.
        import importlib.util
        from pathlib import Path

        migration_path = (
            Path(__file__).resolve().parents[2]
            / "alembic"
            / "versions"
            / "d860a0a0a001_add_order_share_tokens_and_ai_digests.py"
        )
        spec = importlib.util.spec_from_file_location(
            "d860_migration", migration_path
        )
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # The migration uses `from alembic import op` — re-bind for this
        # test by patching the module reference.
        mod.op = op  # type: ignore[attr-defined]
        mod.upgrade()

        # Verify tables exist
        from sqlalchemy import inspect

        insp = inspect(conn)
        assert "order_share_tokens" in insp.get_table_names()
        assert "ai_digests" in insp.get_table_names()

        mod.downgrade()
        insp = inspect(conn)
        assert "order_share_tokens" not in insp.get_table_names()
        assert "ai_digests" not in insp.get_table_names()


# ---------------------------------------------------------------------------
# DB-backed: repository cap + revoke + access
# ---------------------------------------------------------------------------


async def _seed_order_and_user(session) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert minimal Hospital + Order + User rows so FK constraints pass."""
    from app.models import Hospital, Order, User
    from app.models.order import OrderStatus, ServiceType
    from app.models.user import UserRole

    user = User(
        id=uuid.uuid4(),
        phone=f"139{uuid.uuid4().int % 100000000:08d}",
        role=UserRole.patient,
    )
    session.add(user)
    await session.flush()

    hospital = Hospital(
        id=uuid.uuid4(),
        name=f"Test Hospital {uuid.uuid4().hex[:6]}",
    )
    session.add(hospital)
    await session.flush()

    order = Order(
        id=uuid.uuid4(),
        order_number=f"YLA-{uuid.uuid4().hex[:10].upper()}",
        patient_id=user.id,
        hospital_id=hospital.id,
        companion_id=None,
        service_type=ServiceType.full_accompany,
        status=OrderStatus.in_progress,
        appointment_date="2026-06-01",
        appointment_time="09:00",
        price=Decimal("299.00"),
    )
    session.add(order)
    await session.flush()
    return order.id, user.id


@pytest.mark.asyncio
async def test_create_with_active_cap_revokes_oldest_when_over_cap():
    async with test_session_factory() as session:
        order_id, user_id = await _seed_order_and_user(session)
        repo = OrderShareTokenRepository(session)

        tokens = []
        for _ in range(4):
            t = await repo.create_with_active_cap(
                order_id=order_id,
                created_by=user_id,
                order_completed_at=None,
            )
            tokens.append(t)
            # Slight stagger so created_at ordering is unambiguous.
            await asyncio.sleep(0.005)
        await session.commit()

        # 4 inserts, cap=3 → oldest must be auto-revoked.
        all_rows = (
            await session.execute(
                select(OrderShareToken).where(OrderShareToken.order_id == order_id)
            )
        ).scalars().all()
        assert len(all_rows) == 4

        active = [r for r in all_rows if r.revoked_at is None]
        assert len(active) == 3, "active token cap = 3 violated"

        revoked = [r for r in all_rows if r.revoked_at is not None]
        assert len(revoked) == 1
        assert revoked[0].id == tokens[0].id, "oldest token must be revoked"
        assert revoked[0].revoked_by == user_id


@pytest.mark.asyncio
async def test_token_uniqueness_enforced_at_db_layer():
    async with test_session_factory() as session:
        order_id, user_id = await _seed_order_and_user(session)
        repo = OrderShareTokenRepository(session)
        t1 = await repo.create_with_active_cap(
            order_id=order_id, created_by=user_id, order_completed_at=None
        )
        await session.commit()

        # Insert duplicate token by hand — must raise IntegrityError.
        from sqlalchemy.exc import IntegrityError

        dup = OrderShareToken(
            order_id=order_id,
            created_by=user_id,
            token=t1.token,
            share_scope=ShareScope.FULL,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()


@pytest.mark.asyncio
async def test_share_scope_defaults_full_and_switchable():
    async with test_session_factory() as session:
        order_id, user_id = await _seed_order_and_user(session)
        repo = OrderShareTokenRepository(session)

        default = await repo.create_with_active_cap(
            order_id=order_id, created_by=user_id, order_completed_at=None
        )
        progress = await repo.create_with_active_cap(
            order_id=order_id,
            created_by=user_id,
            order_completed_at=None,
            share_scope=ShareScope.PROGRESS_ONLY,
        )
        await session.commit()

        assert default.share_scope == ShareScope.FULL
        assert progress.share_scope == ShareScope.PROGRESS_ONLY


@pytest.mark.asyncio
async def test_revoke_marks_inactive():
    async with test_session_factory() as session:
        order_id, user_id = await _seed_order_and_user(session)
        repo = OrderShareTokenRepository(session)

        t = await repo.create_with_active_cap(
            order_id=order_id, created_by=user_id, order_completed_at=None
        )
        await session.commit()
        assert t.is_active is True

        await repo.revoke(t, revoked_by=user_id)
        await session.commit()
        assert t.revoked_at is not None
        assert t.is_active is False


@pytest.mark.asyncio
async def test_record_access_aggregates_distinct_openid():
    async with test_session_factory() as session:
        order_id, user_id = await _seed_order_and_user(session)
        repo = OrderShareTokenRepository(session)
        t = await repo.create_with_active_cap(
            order_id=order_id, created_by=user_id, order_completed_at=None
        )
        await session.commit()

        await repo.record_access(t, accessor_openid="openid-A")
        await repo.record_access(t, accessor_openid="openid-A")  # same openid
        await repo.record_access(t, accessor_openid="openid-B")
        await session.commit()

        assert t.first_accessor_openid == "openid-A"
        assert t.distinct_accessor_count == 2
        assert t.first_accessed_at is not None
        assert t.last_accessed_at >= t.first_accessed_at


@pytest.mark.asyncio
async def test_ai_digest_unique_per_order_and_default_status():
    async with test_session_factory() as session:
        order_id, _ = await _seed_order_and_user(session)

        digest = AIDigest(order_id=order_id, summary=None)
        session.add(digest)
        await session.flush()
        assert digest.status == AIDigestStatus.PENDING
        assert digest.cost_yuan == Decimal("0.0000")

        from sqlalchemy.exc import IntegrityError

        dup = AIDigest(order_id=order_id, summary="dup")
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
