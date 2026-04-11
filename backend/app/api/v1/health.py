from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import text

from app.database import async_session

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/readiness")
async def readiness():
    try:
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready", "db": "ok"}
    except Exception:
        return {"status": "not_ready", "db": "error"}
