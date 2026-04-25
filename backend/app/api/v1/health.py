"""Health & Readiness endpoints.

Liveness (`/health`):  process-only, always 200 if FastAPI is responsive.
Readiness (`/readiness`):  checks 5 dependencies (DB, Redis, Alembic version,
Payment provider, SMS provider).  Returns 200 only if every required check
passes; otherwise 503.

Per-check timeouts are enforced so the whole endpoint stays well under the
1.5 s p99 budget required for K8s/ACA readiness probes:
  * db        — 1.0 s   (SELECT 1)
  * redis     — 0.5 s   (PING + roundtrip)
  * alembic   — 1.0 s   (read alembic_version table, compare to script head)
  * payment   — 0.8 s   (mock = instant; real = sandbox HEAD with fallback)
  * sms       — 0.2 s   (mock = instant; real = config completeness only)
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import settings
from app.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


# ---------------------------------------------------------------------------
# Liveness
# ---------------------------------------------------------------------------
@router.get(
    "/health",
    summary="健康检查（liveness）",
    description="liveness 探针：进程活着即返回 200，不检查外部依赖。",
)
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


# ---------------------------------------------------------------------------
# Per-dependency check helpers
# ---------------------------------------------------------------------------
DB_TIMEOUT_S = 1.0
REDIS_TIMEOUT_S = 0.5
ALEMBIC_TIMEOUT_S = 1.0
PAYMENT_TIMEOUT_S = 0.8
SMS_TIMEOUT_S = 0.2


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


async def _check_db() -> dict[str, Any]:
    start = time.perf_counter()
    try:
        async def _do() -> None:
            async with async_session() as session:
                await session.execute(text("SELECT 1"))

        await asyncio.wait_for(_do(), timeout=DB_TIMEOUT_S)
        return {"status": "ok", "latency_ms": _ms(start)}
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"timeout >{int(DB_TIMEOUT_S * 1000)}ms",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
        }


async def _check_redis(request: Request) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        redis = getattr(request.app.state, "redis", None)
        if redis is None:
            raise RuntimeError("redis client not initialized")

        async def _do() -> None:
            pong = await redis.ping()
            if pong is False:
                raise RuntimeError("redis PING returned False")
            # extra set/get roundtrip kept for FakeRedis injection compatibility
            await redis.set("readiness_check", "1", ex=10)
            val = await redis.get("readiness_check")
            if val is None:
                raise RuntimeError("redis readback returned None")

        await asyncio.wait_for(_do(), timeout=REDIS_TIMEOUT_S)
        return {"status": "ok", "latency_ms": _ms(start)}
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"timeout >{int(REDIS_TIMEOUT_S * 1000)}ms",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
        }


# Cached at process startup (see prime_alembic_head_cache) so /readiness
# does NOT pay the alembic-import cost on every probe (~50-200ms saved).
# Sentinel `_UNSET` distinguishes "not yet primed" from "primed = None".
_UNSET: Any = object()
_ALEMBIC_HEAD_CACHE: Any = _UNSET


def _readiness_skip_migration_check() -> bool:
    """Escape hatch: set READINESS_SKIP_MIGRATION_CHECK=1 to bypass the
    alembic version-drift check during emergency rollouts."""
    return os.getenv("READINESS_SKIP_MIGRATION_CHECK", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _alembic_script_head() -> str | None:
    """Return current head revision id from the bundled alembic scripts.

    Result is cached after the first successful read; call
    ``prime_alembic_head_cache()`` from app startup to warm it.
    """
    global _ALEMBIC_HEAD_CACHE
    if _ALEMBIC_HEAD_CACHE is not _UNSET:
        return _ALEMBIC_HEAD_CACHE

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    # alembic.ini lives at backend/alembic.ini (cwd in tests = backend/)
    cfg_paths = [
        Path("alembic.ini"),
        Path(__file__).resolve().parents[3] / "alembic.ini",
    ]
    cfg_path = next((p for p in cfg_paths if p.exists()), None)
    if cfg_path is None:
        raise RuntimeError("alembic.ini not found")
    cfg = Config(str(cfg_path))
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) > 1:
        raise RuntimeError(f"multiple alembic heads: {heads}")
    head = heads[0] if heads else None
    _ALEMBIC_HEAD_CACHE = head
    return head


def prime_alembic_head_cache() -> str | None:
    """Eagerly load and cache the alembic head revision at app startup.

    Failures are swallowed (logged) so a broken alembic config does not
    block process boot — the on-demand path in `_check_alembic` will retry
    on the next probe and surface the error as `status: error` then.
    """
    global _ALEMBIC_HEAD_CACHE
    try:
        head = _alembic_script_head()
        logger.info("Alembic head cached at startup: %s", head)
        return head
    except Exception as exc:  # noqa: BLE001
        # Reset so the next probe will retry (and report the error).
        _ALEMBIC_HEAD_CACHE = _UNSET
        logger.warning("Failed to prime alembic head cache: %s", exc)
        return None


def _reset_alembic_head_cache() -> None:
    """Test helper: clear the cached head revision."""
    global _ALEMBIC_HEAD_CACHE
    _ALEMBIC_HEAD_CACHE = _UNSET


async def _check_alembic() -> dict[str, Any]:
    start = time.perf_counter()
    if _readiness_skip_migration_check():
        return {
            "status": "skipped",
            "reason": "READINESS_SKIP_MIGRATION_CHECK=1",
            "latency_ms": _ms(start),
        }
    try:
        async def _do() -> dict[str, Any]:
            head = await asyncio.to_thread(_alembic_script_head)
            current: str | None = None
            try:
                async with async_session() as session:
                    res = await session.execute(text("SELECT version_num FROM alembic_version"))
                    row = res.first()
                    current = row[0] if row else None
            except Exception:
                # alembic_version table may not exist (e.g. SQLite test env where
                # we used metadata.create_all instead of running migrations).
                # In that case treat current=None as a soft state.
                current = None

            if current is None:
                # No alembic_version row: only OK if there are no migrations either.
                if head is None:
                    return {"status": "ok", "current": None, "head": None}
                return {
                    "status": "error",
                    "current": None,
                    "head": head,
                    "error": f"migration drift: db=None head={head}",
                }
            if current != head:
                return {
                    "status": "error",
                    "current": current,
                    "head": head,
                    "error": f"migration drift: db={current} head={head}",
                }
            return {"status": "ok", "current": current, "head": head}

        result = await asyncio.wait_for(_do(), timeout=ALEMBIC_TIMEOUT_S)
        result["latency_ms"] = _ms(start)
        return result
    except asyncio.TimeoutError:
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"timeout >{int(ALEMBIC_TIMEOUT_S * 1000)}ms",
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "error",
            "latency_ms": _ms(start),
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
        }


async def _check_payment() -> dict[str, Any]:
    start = time.perf_counter()
    mode = settings.payment_provider or "mock"
    if mode == "mock":
        return {"status": "skipped", "mode": "mock", "latency_ms": _ms(start)}

    # real mode: ping wechatpay sandbox host but do NOT block readiness on
    # external network — degrade gracefully.
    try:
        import httpx

        async def _do() -> None:
            async with httpx.AsyncClient(timeout=PAYMENT_TIMEOUT_S) as c:
                # api.mch.weixin.qq.com is the production base; we use HEAD
                # which is cheap and does not consume API quota.
                await c.head("https://api.mch.weixin.qq.com/")

        await asyncio.wait_for(_do(), timeout=PAYMENT_TIMEOUT_S)
        return {"status": "ok", "mode": mode, "latency_ms": _ms(start)}
    except Exception as exc:  # noqa: BLE001
        # 503 fallback: mark as degraded but DO NOT fail readiness — payment
        # outage shouldn't take down the whole API. Status "degraded" is
        # treated as non-fatal by _aggregate.
        return {
            "status": "degraded",
            "mode": mode,
            "latency_ms": _ms(start),
            "error": f"{exc.__class__.__name__}: {exc}"[:200],
        }


async def _check_sms() -> dict[str, Any]:
    start = time.perf_counter()
    mode = settings.sms_provider or "mock"
    if mode == "mock":
        return {"status": "skipped", "mode": "mock", "latency_ms": _ms(start)}

    # real mode: do NOT actually send a (paid) SMS; only validate config
    missing = [
        name
        for name, val in [
            ("sms_access_key", settings.sms_access_key),
            ("sms_access_secret", settings.sms_access_secret),
            ("sms_sign_name", settings.sms_sign_name),
            ("sms_template_code", settings.sms_template_code),
        ]
        if not val
    ]
    if missing:
        return {
            "status": "error",
            "mode": mode,
            "latency_ms": _ms(start),
            "error": f"missing config: {', '.join(missing)}",
        }
    return {"status": "ok", "mode": mode, "latency_ms": _ms(start)}


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
# A check is considered fatal (→ 503) when its status is "error".
# "ok" / "skipped" / "degraded" all keep readiness=true.
_FATAL_STATUSES = {"error"}


async def _run_readiness_checks(request: Request) -> tuple[bool, dict[str, Any]]:
    db, redis_, alembic_, payment, sms = await asyncio.gather(
        _check_db(),
        _check_redis(request),
        _check_alembic(),
        _check_payment(),
        _check_sms(),
    )
    checks = {
        "db": db,
        "redis": redis_,
        "alembic": alembic_,
        "payment": payment,
        "sms": sms,
    }
    all_ok = not any(c.get("status") in _FATAL_STATUSES for c in checks.values())
    return all_ok, checks


def _readiness_response(all_ok: bool, checks: dict[str, Any]):
    body = {
        "ready": all_ok,
        # backward-compat fields used by older probes / dashboards
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
    }
    if not all_ok:
        return JSONResponse(status_code=503, content=body)
    return body


@router.get(
    "/readiness",
    summary="就绪检查（readiness）",
    description=(
        "串行检查 5 项依赖：PostgreSQL（SELECT 1）、Redis（PING）、Alembic 版本、"
        "Payment 提供方、SMS 提供方。任一 error → 503；degraded/skipped 视为通过。"
    ),
)
async def readiness(request: Request):
    all_ok, checks = await _run_readiness_checks(request)
    return _readiness_response(all_ok, checks)
