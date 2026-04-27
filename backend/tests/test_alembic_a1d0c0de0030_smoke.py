"""Smoke test: alembic ``a1d0c0de0030`` (money -> Decimal) up/down round-trip.

ADR-0030 introduced ``Numeric(10,2)`` for ``orders.price`` and
``payments.amount``. This migration was unverified for some time; the W18
post-mortem flagged it as a follow-up.

Why Postgres-only: several upstream migrations use PG-specific DDL
(``DO $$`` blocks, ``ALTER TYPE ... ADD VALUE``), so a pure SQLite walk
runs aground long before reaching ``a1d0c0de0030``. We therefore gate
this test on a reachable Postgres test instance via the
``ALEMBIC_SMOKE_DATABASE_URL`` env var (asyncpg URL). Local dev usually
has the ``backend-db-1`` container available; CI may inject its own URL.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest


REVISION = "a1d0c0de0030"
PARENT = "b2b5c0f247c3"


def _smoke_url() -> str | None:
    """Return a Postgres async URL suitable for a smoke DB if one is
    configured, else ``None``.
    """
    explicit = os.environ.get("ALEMBIC_SMOKE_DATABASE_URL")
    if explicit:
        return explicit
    base = os.environ.get("DATABASE_URL")
    if not base or "postgresql" not in base or "?" in base:
        return None
    if "+asyncpg" not in base:
        base = base.replace("postgresql://", "postgresql+asyncpg://", 1)
    return base.rstrip("/") + "_smoke_a1d0c0de0030"


smoke_url = _smoke_url()


async def _drop_create_db(admin_url: str, target_db: str) -> None:
    import asyncpg

    parsed = urlparse(admin_url)
    user = parsed.username or "postgres"
    pw = parsed.password or ""
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 5432
    conn = await asyncpg.connect(
        user=user, password=pw, host=host, port=port, database="postgres"
    )
    try:
        await conn.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{target_db}' AND pid <> pg_backend_pid()"
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{target_db}"')
        await conn.execute(f'CREATE DATABASE "{target_db}"')
    finally:
        await conn.close()


async def _drop_db(admin_url: str, target_db: str) -> None:
    import asyncpg

    parsed = urlparse(admin_url)
    conn = await asyncpg.connect(
        user=parsed.username or "postgres",
        password=parsed.password or "",
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 5432,
        database="postgres",
    )
    try:
        await conn.execute(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname='{target_db}' AND pid <> pg_backend_pid()"
        )
        await conn.execute(f'DROP DATABASE IF EXISTS "{target_db}"')
    finally:
        await conn.close()


async def _column_data_type(async_url: str, column: str) -> tuple[str, int | None, int | None]:
    import asyncpg

    parsed = urlparse(async_url.replace("+asyncpg", ""))
    conn = await asyncpg.connect(
        user=parsed.username or "postgres",
        password=parsed.password or "",
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 5432,
        database=parsed.path.lstrip("/"),
    )
    try:
        row = await conn.fetchrow(
            "SELECT data_type, numeric_precision, numeric_scale "
            "FROM information_schema.columns "
            "WHERE table_name='orders' AND column_name=$1",
            column,
        )
    finally:
        await conn.close()
    if row is None:
        raise AssertionError(f"orders.{column} not found")
    return row["data_type"], row["numeric_precision"], row["numeric_scale"]


@pytest.mark.skipif(
    smoke_url is None,
    reason="ALEMBIC_SMOKE_DATABASE_URL / DATABASE_URL not set; skipping PG smoke",
)
def test_alembic_a1d0c0de0030_round_trip_postgres():
    """Run upgrade -> downgrade -> upgrade against a real Postgres DB and
    verify ``orders.price`` ends up as ``numeric(10,2)``.
    """
    from alembic import command
    from alembic.config import Config

    parsed = urlparse(smoke_url)
    target_db = parsed.path.lstrip("/")
    async_url = smoke_url
    admin_url_for_dropcreate = urlunparse(parsed._replace(path="/postgres"))

    asyncio.run(_drop_create_db(admin_url_for_dropcreate, target_db))

    backend_root = Path(__file__).resolve().parents[1]
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    os.environ["ALEMBIC_DATABASE_URL"] = async_url

    try:
        command.upgrade(cfg, REVISION)
        data_type, precision, scale = asyncio.run(
            _column_data_type(async_url, "price")
        )
        assert data_type == "numeric", data_type
        assert precision == 10
        assert scale == 2

        command.downgrade(cfg, PARENT)
        data_type, _, _ = asyncio.run(_column_data_type(async_url, "price"))
        assert data_type in ("double precision", "real"), data_type

        command.upgrade(cfg, REVISION)
        data_type, _, _ = asyncio.run(_column_data_type(async_url, "price"))
        assert data_type == "numeric"
    finally:
        asyncio.run(_drop_db(admin_url_for_dropcreate, target_db))


def test_a1d0c0de0030_revision_metadata_intact():
    """Cheap structural assertion that runs everywhere: the revision file
    declares the right parent and is referenced by ``c0ffee029001``.
    """
    backend_root = Path(__file__).resolve().parents[1]
    rev = (
        backend_root
        / "alembic"
        / "versions"
        / "a1d0c0de0030_money_to_decimal_adr_0030.py"
    )
    text = rev.read_text(encoding="utf-8")
    assert f'revision = "{REVISION}"' in text
    assert f'down_revision = "{PARENT}"' in text
    assert '"orders"' in text and '"price"' in text
    assert '"payments"' in text and '"amount"' in text

    pii = (
        backend_root
        / "alembic"
        / "versions"
        / "c0ffee029001_emergency_pii_encryption.py"
    )
    assert f'down_revision = "{REVISION}"' in pii.read_text(encoding="utf-8")
