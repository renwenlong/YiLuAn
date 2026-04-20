import uuid

import pytest


@pytest.mark.asyncio
class TestHospitals:
    async def test_search_hospitals_empty(self, client):
        resp = await client.get("/api/v1/hospitals")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_seed_hospitals(self, client):
        resp = await client.post("/api/v1/hospitals/seed")
        assert resp.status_code == 200
        data = resp.json()
        assert data["seeded"] == 111

    async def test_search_hospitals_keyword(self, client, seed_hospital):
        await seed_hospital(name="北京协和医院")
        await seed_hospital(name="北京天坛医院")
        await seed_hospital(name="上海瑞金医院")
        resp = await client.get("/api/v1/hospitals?keyword=北京")
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_search_hospitals_pagination(self, client, seed_hospital):
        for i in range(5):
            await seed_hospital(name=f"测试医院{i}")
        resp = await client.get("/api/v1/hospitals?page=1&page_size=2")
        data = resp.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    async def test_get_hospital_detail(self, client, seed_hospital):
        h = await seed_hospital(name="北京协和医院", level="三甲")
        resp = await client.get(f"/api/v1/hospitals/{h.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "北京协和医院"
        assert data["level"] == "三甲"

    async def test_get_hospital_not_found(self, client):
        resp = await client.get(f"/api/v1/hospitals/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_search_hospitals_no_keyword(self, client, seed_hospital):
        await seed_hospital(name="医院A")
        await seed_hospital(name="医院B")
        resp = await client.get("/api/v1/hospitals")
        data = resp.json()
        assert data["total"] == 2

    async def test_seed_hospitals_idempotent(self, client):
        await client.post("/api/v1/hospitals/seed")
        resp = await client.post("/api/v1/hospitals/seed")
        data = resp.json()
        assert data["seeded"] == 111


@pytest.mark.asyncio
class TestHospitalsCache:
    """Redis cache tests for the hospital search endpoint."""

    async def test_cache_miss_writes_cache(self, client, seed_hospital, fake_redis):
        """On cache miss, DB is queried and result is written to Redis."""
        await seed_hospital(name="缓存测试医院")
        resp = await client.get("/api/v1/hospitals?city=")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

        # Verify cache was written
        from app.api.v1.hospitals import _cache_key

        key = _cache_key(None, None, None, None, None, None, 1, 20)
        cached = await fake_redis.get(key)
        assert cached is not None
        import json

        data = json.loads(cached)
        assert data["total"] == 1

    async def test_cache_hit_skips_db(self, client, fake_redis):
        """On cache hit, the cached JSON is returned without touching DB."""
        import json

        from app.api.v1.hospitals import _cache_key

        key = _cache_key(None, None, None, None, None, None, 1, 20)
        payload = json.dumps({"items": [], "total": 999})
        await fake_redis.set(key, payload)

        resp = await client.get("/api/v1/hospitals")
        assert resp.status_code == 200
        # total=999 proves response came from cache, not DB
        assert resp.json()["total"] == 999

    async def test_cache_expired_re_queries_db(self, client, seed_hospital, fake_redis):
        """After cache is cleared (simulating TTL expiry), DB is queried again."""
        await seed_hospital(name="过期测试医院")
        from app.api.v1.hospitals import _cache_key

        key = _cache_key(None, None, None, None, None, None, 1, 20)

        # First request populates cache
        resp1 = await client.get("/api/v1/hospitals")
        assert resp1.json()["total"] == 1

        # Simulate TTL expiry by deleting the cache key
        await fake_redis.delete(key)

        # Second request should re-query DB
        resp2 = await client.get("/api/v1/hospitals")
        assert resp2.json()["total"] == 1

        # Cache should be re-populated
        cached = await fake_redis.get(key)
        assert cached is not None
