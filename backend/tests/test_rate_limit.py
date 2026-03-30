import pytest

from app.core.rate_limit import limiter


pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def reset_rate_limiter():
    """Reset rate limiter state between tests."""
    limiter.reset()
    yield
    limiter.reset()


class TestRateLimit:
    async def test_otp_rate_limit(self, client, fake_redis):
        """After 5 OTP requests, the 6th should return 429."""
        for i in range(5):
            resp = await client.post(
                "/api/v1/auth/send-otp",
                json={"phone": f"1380013900{i}"},
            )
            # Should succeed (not rate limited)
            assert resp.status_code != 429, f"Request {i+1} got rate limited"

        resp = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "13800139099"},
        )
        assert resp.status_code == 429

    async def test_normal_request_under_limit(self, client):
        """A normal GET should work fine under the default rate limit."""
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_rate_limit_returns_429(self, client, fake_redis):
        """Rate-limited responses should return 429."""
        for i in range(6):
            resp = await client.post(
                "/api/v1/auth/send-otp",
                json={"phone": f"1380013800{i}"},
            )
        assert resp.status_code == 429
