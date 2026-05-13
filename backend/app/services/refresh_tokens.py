"""Server-side refresh-token rotation & revocation backed by Redis.

Background (security fix 2026-05-13):
    Previously ``AuthService.refresh_token`` just decoded the JWT and minted a
    new pair — the old refresh remained usable for its full 7-day lifetime,
    and logout / account-disable could not revoke it. This module gives every
    refresh token a unique ``jti`` and tracks the set of *currently valid*
    jtis per user in Redis.

Semantics:
  * ``issue(user_id, jti, ttl)`` — record a freshly minted refresh as valid.
  * ``rotate(user_id, old_jti, new_jti, ttl)`` — atomically retire the old
    jti and admit a new one. Returns ``True`` if the old jti was valid.
  * ``rotate`` returning ``False`` means **token reuse / replay** — callers
    MUST treat it as a credential compromise: invoke ``revoke_all(user_id)``
    and reject the request. (Strategy (b): kill every session of that user.)
  * ``revoke_all(user_id)`` — wipe every active refresh jti for a user. Used
    by logout, soft-delete, and disable.

Redis layout:
  * ``refresh:user:{user_id}``   — SET of currently valid jti strings.
  * ``refresh:jti:{user_id}:{jti}`` — marker key with TTL = refresh expiry.

Failure mode:
  Redis unreachable → every operation raises. AuthService translates that to
  a 401 (fail-closed); refresh is high-value, better to log users out than
  silently disable rotation.
"""
from __future__ import annotations

import logging

import redis.asyncio as aioredis


logger = logging.getLogger(__name__)


def _user_set_key(user_id: str) -> str:
    return f"refresh:user:{user_id}"


def _jti_key(user_id: str, jti: str) -> str:
    return f"refresh:jti:{user_id}:{jti}"


class RefreshTokenStore:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client

    async def issue(self, user_id: str, jti: str, ttl_seconds: int) -> None:
        """Record ``jti`` as a freshly issued, currently valid refresh."""
        pipe = self.redis.pipeline()
        pipe.sadd(_user_set_key(user_id), jti)
        # Align user-set TTL with the longest-living jti so an abandoned user
        # eventually self-cleans.
        pipe.expire(_user_set_key(user_id), ttl_seconds)
        pipe.set(_jti_key(user_id, jti), "1", ex=ttl_seconds)
        await pipe.execute()

    async def is_valid(self, user_id: str, jti: str) -> bool:
        return bool(await self.redis.sismember(_user_set_key(user_id), jti))

    async def rotate(
        self, user_id: str, old_jti: str, new_jti: str, ttl_seconds: int
    ) -> bool:
        """Retire ``old_jti``; admit ``new_jti`` iff old was valid.

        Returns True on a clean rotation. Returns False if ``old_jti`` was NOT
        in the active set — meaning the caller is replaying an already-rotated
        (or never-issued) token. Caller MUST then revoke_all.

        SREM is atomic and returns 1 only for the first remover, so concurrent
        rotation attempts on the same jti can only succeed once.
        """
        removed = await self.redis.srem(_user_set_key(user_id), old_jti)
        if not removed:
            return False
        # Best-effort cleanup of per-jti marker; ignore if already gone.
        await self.redis.delete(_jti_key(user_id, old_jti))
        await self.issue(user_id, new_jti, ttl_seconds)
        return True

    async def revoke_all(self, user_id: str) -> int:
        """Drop every active refresh jti for ``user_id``. Returns count."""
        set_key = _user_set_key(user_id)
        jtis = await self.redis.smembers(set_key)
        if not jtis:
            return 0
        pipe = self.redis.pipeline()
        for jti in jtis:
            j = jti.decode() if isinstance(jti, (bytes, bytearray)) else jti
            pipe.delete(_jti_key(user_id, j))
        pipe.delete(set_key)
        await pipe.execute()
        return len(jtis)
