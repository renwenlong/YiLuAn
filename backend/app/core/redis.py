import redis.asyncio as aioredis
import redis as redis_sync
from fastapi import Request

from app.config import settings


def init_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


def init_redis_sync() -> redis_sync.Redis:
    """Sync redis client — 仅用于实源 sync 路径（如 distributed CB
    的 SETNX probe_lock、ADR-0040 Phase 1）。与 async client 同路一个
    Redis 实例，不引入新依赖。
    """
    return redis_sync.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis
