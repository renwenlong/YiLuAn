import redis.asyncio as aioredis
from fastapi import Request

from app.config import settings


def init_redis() -> aioredis.Redis:
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


def get_redis(request: Request) -> aioredis.Redis:
    return request.app.state.redis
