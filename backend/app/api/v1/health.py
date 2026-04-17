from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health", summary="健康检查（liveness）", description="liveness 探针：进程活着即返回 200，不检查外部依赖。")
async def health():
    """Liveness probe: 只要进程能响应就返回 200，不查 DB/Redis。"""
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


async def _run_readiness_checks(request: Request) -> tuple[bool, dict]:
    """执行 DB + Redis 就绪检查，返回 (all_ok, checks_dict)。

    checks_dict 形如 {"db": "ok", "redis": "error: <msg>"}
    """
    checks: dict[str, str] = {}

    # Check database: SELECT 1
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["db"] = f"error: {exc.__class__.__name__}: {exc}"[:200]

    # Check Redis: PING
    try:
        redis = request.app.state.redis
        if redis is None:
            raise RuntimeError("redis client not initialized")
        # 优先使用 PING（更轻量），失败则回退到 set/get 兼容 fakeredis 下的异常注入
        pong = await redis.ping()
        if pong is False:
            raise RuntimeError("redis PING returned False")
        # 额外的 set/get 往返，便于测试 mock 注入异常（与原实现保持兼容）
        await redis.set("readiness_check", "1", ex=10)
        val = await redis.get("readiness_check")
        if val is None:
            raise RuntimeError("redis readback returned None")
        checks["redis"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["redis"] = f"error: {exc.__class__.__name__}: {exc}"[:200]

    all_ok = all(v == "ok" for v in checks.values())
    return all_ok, checks


def _readiness_response(all_ok: bool, checks: dict) -> JSONResponse | dict:
    body = {
        "status": "ready" if all_ok else "not_ready",
        "checks": checks,
        # 向后兼容字段（历史测试/探针脚本可能依赖扁平键）
        "db": "ok" if checks.get("db") == "ok" else "error",
        "redis": "ok" if checks.get("redis") == "ok" else "error",
    }
    if not all_ok:
        return JSONResponse(status_code=503, content=body)
    return body


@router.get(
    "/readiness",
    summary="就绪检查（readiness）",
    description="检查数据库（SELECT 1）和 Redis（PING）连接。全部 OK → 200；任一失败 → 503。",
)
async def readiness(request: Request):
    all_ok, checks = await _run_readiness_checks(request)
    return _readiness_response(all_ok, checks)
