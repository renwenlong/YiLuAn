"""Unit tests for probe_redis_required_for_complaint_rate.

AC#6 (S3-OPS-COMPLAINT-RATE-REDIS-REQUIRED-PROBE):
  case 1: redis ON + ZSET op OK → probe pass
  case 2: redis None (init_redis raise / from_url fail) → probe raise
  case 3: redis OP raise (mock zadd raise) → probe raise

Sentinel: SECRET_REDIS_REQUIRED_PROBE_TEST_42 grep-defense (反案 #15).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.probes import probe_redis_required_for_complaint_rate

# Sentinel for grep / rg 防误删 (反案 #15).
_SECRET_REDIS_REQUIRED_PROBE_TEST_42 = "SECRET_REDIS_REQUIRED_PROBE_TEST_42_DO_NOT_LEAK"


class TestProbeRedisRequiredForComplaintRate:
    """3 case AC#6."""

    @pytest.mark.asyncio
    async def test_case1_redis_on_op_ok_probe_pass(self) -> None:
        """case 1: redis ON + zadd/zrangebyscore OK → no raise."""
        fake_redis = AsyncMock()

        # Capture zadd member to echo back from zrangebyscore (simulate real round-trip)
        captured = {}

        async def _zadd(key, mapping):
            captured["member"] = next(iter(mapping.keys()))
            return 1

        async def _zrangebyscore(key, min, max, withscores=False):
            # Must include the captured member so probe sees round-trip success
            return [captured.get("member", "")]

        async def _expire(key, ttl):
            return True

        async def _aclose():
            return None

        fake_redis.zadd = _zadd
        fake_redis.zrangebyscore = _zrangebyscore
        fake_redis.expire = _expire
        fake_redis.aclose = _aclose

        with patch("app.core.redis.init_redis", return_value=fake_redis):
            # Should not raise
            await probe_redis_required_for_complaint_rate()

    @pytest.mark.asyncio
    async def test_case2_redis_none_probe_raise(self) -> None:
        """case 2: init_redis raise (e.g. malformed URL) → probe raise RuntimeError."""

        def _raise_init_redis():
            raise ConnectionError("redis 不可达 (REDIS_URL 错或网络阻断)")

        # init_redis 自己 raise — probe 应该包成 RuntimeError 抛出
        with patch("app.core.redis.init_redis", side_effect=_raise_init_redis):
            with pytest.raises(RuntimeError, match="redis_required_for_complaint_rate"):
                await probe_redis_required_for_complaint_rate()

    @pytest.mark.asyncio
    async def test_case3_zadd_raise_probe_raise(self) -> None:
        """case 3: redis 拿到 client 但 zadd raise → probe raise RuntimeError."""
        fake_redis = AsyncMock()

        async def _zadd_raise(*args, **kwargs):
            raise ConnectionError("redis op timeout / 节点 down")

        async def _aclose():
            return None

        fake_redis.zadd = _zadd_raise
        fake_redis.aclose = _aclose

        with patch("app.core.redis.init_redis", return_value=fake_redis):
            with pytest.raises(RuntimeError, match="redis_required_for_complaint_rate"):
                await probe_redis_required_for_complaint_rate()

    @pytest.mark.asyncio
    async def test_case3b_zrangebyscore_raise_probe_raise(self) -> None:
        """case 3 变体: zadd OK 但 zrangebyscore raise → probe raise (双侧 op 校验)."""
        fake_redis = AsyncMock()

        async def _zadd(key, mapping):
            return 1

        async def _zrange_raise(*args, **kwargs):
            raise AttributeError("zrangebyscore not implemented on client")

        async def _aclose():
            return None

        fake_redis.zadd = _zadd
        fake_redis.zrangebyscore = _zrange_raise
        fake_redis.aclose = _aclose

        with patch("app.core.redis.init_redis", return_value=fake_redis):
            with pytest.raises(RuntimeError, match="redis_required_for_complaint_rate"):
                await probe_redis_required_for_complaint_rate()

    @pytest.mark.asyncio
    async def test_case3c_zrangebyscore_returns_empty_probe_raise(self) -> None:
        """case 3 变体: zadd OK, zrangebyscore 返空 (cluster 写读不一致) → probe raise."""
        fake_redis = AsyncMock()

        async def _zadd(key, mapping):
            return 1

        async def _zrange_empty(*args, **kwargs):
            return []  # round-trip 失败 (写入但读不回)

        async def _expire(*args, **kwargs):
            return True

        async def _aclose():
            return None

        fake_redis.zadd = _zadd
        fake_redis.zrangebyscore = _zrange_empty
        fake_redis.expire = _expire
        fake_redis.aclose = _aclose

        with patch("app.core.redis.init_redis", return_value=fake_redis):
            with pytest.raises(RuntimeError, match="zadd 写入成功但 zrangebyscore 读不回"):
                await probe_redis_required_for_complaint_rate()

    @pytest.mark.asyncio
    async def test_aclose_failure_not_fatal(self) -> None:
        """cleanup aclose 失败不应淹没 probe pass (best-effort)."""
        fake_redis = AsyncMock()

        captured = {}

        async def _zadd(key, mapping):
            captured["member"] = next(iter(mapping.keys()))
            return 1

        async def _zrangebyscore(*args, **kwargs):
            return [captured.get("member", "")]

        async def _expire(*args, **kwargs):
            return True

        async def _aclose_raise():
            raise ConnectionError("aclose failed (cleanup race)")

        fake_redis.zadd = _zadd
        fake_redis.zrangebyscore = _zrangebyscore
        fake_redis.expire = _expire
        fake_redis.aclose = _aclose_raise

        with patch("app.core.redis.init_redis", return_value=fake_redis):
            # Should NOT raise; aclose failure is best-effort
            await probe_redis_required_for_complaint_rate()
