from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/readiness")
async def readiness(request: Request):
    db_status = "ok"
    redis_status = "ok"

    # Check database
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"

    # Check Redis
    try:
        redis = request.app.state.redis
        await redis.set("readiness_check", "1", ex=10)
        val = await redis.get("readiness_check")
        if val is None:
            redis_status = "error"
    except Exception:
        redis_status = "error"

    all_ok = db_status == "ok" and redis_status == "ok"
    body = {
        "status": "ready" if all_ok else "not_ready",
        "db": db_status,
        "redis": redis_status,
    }

    if not all_ok:
        return JSONResponse(status_code=503, content=body)
    return body
