"""Unit tests for `app.services.readonly_complaint_rate_store`."""

from __future__ import annotations

import time

import pytest

from app.services.readonly_complaint_rate_store import (
    REDIS_KEY,
    REDIS_TTL_SECONDS,
    ComplaintRateStore,
    get_complaint_rate_store,
    reset_default_store_for_tests,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _isolate() -> None:
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


# -------------------------------------------------------- in-process fallback


async def test_inproc_record_and_rolling_average() -> None:
    store = ComplaintRateStore(redis_client=None)
    now = time.time()
    await store.record_rate(0.05, ts=now)
    await store.record_rate(0.07, ts=now)
    await store.record_rate(0.03, ts=now)
    avg = await store.get_rolling_average(window_days=7)
    assert avg is not None
    assert abs(avg - 0.05) < 1e-9  # (0.05 + 0.07 + 0.03) / 3


async def test_inproc_no_samples_returns_none() -> None:
    store = ComplaintRateStore(redis_client=None)
    assert await store.get_rolling_average(window_days=7) is None


async def test_inproc_drops_samples_outside_window() -> None:
    store = ComplaintRateStore(redis_client=None)
    now = time.time()
    # sample 10 days ago — outside 7d window
    await store.record_rate(99.0, ts=now - 10 * 86400)
    # sample 1 hour ago — inside
    await store.record_rate(0.05, ts=now - 3600)
    avg = await store.get_rolling_average(window_days=7)
    assert avg is not None
    assert abs(avg - 0.05) < 1e-9  # 99.0 dropped


# ---------------------------------------------------------- redis-backed mode


class _FakeRedis:
    """Minimal redis async stub that mimics ZSET ops the store uses."""

    def __init__(self) -> None:
        self.zset: dict[str, dict[str, float]] = {}
        self.ttls: dict[str, int] = {}

    async def zadd(self, key: str, mapping: dict[str, float]) -> int:
        bucket = self.zset.setdefault(key, {})
        added = 0
        for m, s in mapping.items():
            if m not in bucket:
                added += 1
            bucket[m] = s
        return added

    async def expire(self, key: str, seconds: int) -> bool:
        self.ttls[key] = seconds
        return True

    async def zremrangebyscore(self, key: str, min_score: float, max_score: float) -> int:
        bucket = self.zset.get(key, {})
        removed = [m for m, s in bucket.items() if min_score <= s <= max_score]
        for m in removed:
            bucket.pop(m)
        return len(removed)

    async def zrangebyscore(
        self, key: str, min_score: float, max_score: float, withscores: bool = False
    ) -> list:
        bucket = self.zset.get(key, {})
        return [m for m, s in bucket.items() if min_score <= s <= max_score]


async def test_redis_record_writes_zset_with_ttl() -> None:
    fake = _FakeRedis()
    store = ComplaintRateStore(redis_client=fake)
    await store.record_rate(0.05)
    assert REDIS_KEY in fake.zset
    assert len(fake.zset[REDIS_KEY]) == 1
    assert fake.ttls[REDIS_KEY] == REDIS_TTL_SECONDS


async def test_redis_rolling_average_parses_rate_from_member() -> None:
    fake = _FakeRedis()
    store = ComplaintRateStore(redis_client=fake)
    await store.record_rate(0.1)
    await store.record_rate(0.2)
    avg = await store.get_rolling_average(window_days=7)
    assert avg is not None
    assert abs(avg - 0.15) < 1e-9


async def test_redis_rolling_average_returns_none_when_empty() -> None:
    fake = _FakeRedis()
    store = ComplaintRateStore(redis_client=fake)
    assert await store.get_rolling_average(window_days=7) is None


async def test_redis_handles_bytes_member_from_redis_py() -> None:
    fake = _FakeRedis()
    store = ComplaintRateStore(redis_client=fake)
    await store.record_rate(0.05)
    # simulate redis-py default (decode_responses=False) returning bytes
    bucket = fake.zset[REDIS_KEY]
    fake.zset[REDIS_KEY] = {m.encode("utf-8"): s for m, s in bucket.items()}
    # patch zrangebyscore to also return bytes
    orig = fake.zrangebyscore

    async def _bytes_range(key: str, lo: float, hi: float, withscores: bool = False) -> list:
        return [
            m if isinstance(m, bytes) else m.encode("utf-8")
            for m in await orig(key, lo, hi, withscores)
        ]

    fake.zrangebyscore = _bytes_range  # type: ignore[assignment]
    avg = await store.get_rolling_average(window_days=7)
    assert avg is not None
    assert abs(avg - 0.05) < 1e-9


# ----------------------------------------------------- module-level singleton


async def test_get_complaint_rate_store_returns_singleton_without_redis() -> None:
    s1 = get_complaint_rate_store()
    s2 = get_complaint_rate_store()
    assert s1 is s2


async def test_get_complaint_rate_store_with_redis_returns_new_each_call() -> None:
    fake = _FakeRedis()
    s1 = get_complaint_rate_store(redis_client=fake)
    s2 = get_complaint_rate_store(redis_client=fake)
    assert s1 is not s2  # caller-controlled lifecycle


async def test_record_handles_invalid_member_in_zset_gracefully() -> None:
    fake = _FakeRedis()
    store = ComplaintRateStore(redis_client=fake)
    # plant a malformed member directly (no '@' to split)
    fake.zset[REDIS_KEY] = {"corrupted_no_at_separator": time.time()}
    # should not crash, returns None (only invalid)
    avg = await store.get_rolling_average(window_days=7)
    assert avg is None
