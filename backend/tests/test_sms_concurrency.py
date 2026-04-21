"""SMS OTP concurrency / race-condition tests (A21-12).

Covers gaps left by ``test_sms_blocker.py`` (single-actor brute-force
protection) and ``test_aliyun_sms.py`` (provider-level integration):
real production traffic is concurrent, and rate limits must still hold
when N requests for the same phone / IP race through the event loop at
the same instant.

Three scenarios:

* (a) **Same phone, concurrent** - exercises the per-phone limiter
  (``SMSRateLimiter.check_and_record``). With ``per_minute=1`` exactly
  one of N concurrent calls must win; the rest must be rejected with
  ``per_minute_exceeded`` and a non-zero ``retry_after_seconds`` hint.
  After the 60s window we additionally assert the counter resets
  (monkeypatched ``time.time``) so a follow-up request is allowed.

* (b) **Same IP, different phones, concurrent** - exercises the
  per-IP slowapi limiter on ``POST /api/v1/auth/send-otp``
  (``5/minute`` keyed by remote address). Concurrent OTP requests for
  10 distinct phones from one IP must yield exactly 5 successes and 5
  HTTP 429s (slowapi error envelope).

* (c) **Different phones AND different IPs, concurrent** - the
  control case. With per-phone AND per-IP limiters both unique per
  request, every concurrent send must succeed (no false positives
  from a global counter or shared key collision).

Notes
-----
* The real Redis backend is atomic per-command (INCR/ZADD); FakeRedis
  in the test suite is single-threaded and methods don't await between
  read and write, so the asyncio.gather()s here behave like a real
  redis pipeline. That keeps the test deterministic without mocking.
* Slowapi's per-IP key function is monkeypatched in scenario (c) to
  vary the remote address per request, since httpx's ASGITransport
  pins the client to a single synthetic host.
"""

from __future__ import annotations

import asyncio
import itertools
from typing import Iterator

import pytest

from app.core.rate_limit import limiter as ip_limiter
from app.services.providers.sms.rate_limit import (
    SMSRateLimiter,
    reset_inproc_store,
)


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixture: always reset both limiters between tests to avoid cross-test
# bleed-through (slowapi keeps per-IP state in memory between requests).
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_limiters():
    ip_limiter.reset()
    reset_inproc_store()
    yield
    ip_limiter.reset()
    reset_inproc_store()


# ---------------------------------------------------------------------------
# (a) Same phone, concurrent OTP sends -> per-phone limiter wins exactly once
# ---------------------------------------------------------------------------

class TestSamePhoneConcurrent:
    """Per-phone window (1/min, 5/h) must hold under asyncio.gather."""

    PHONE = "13800000001"

    async def test_only_one_of_n_concurrent_wins(self, fake_redis):
        """10 concurrent ``check_and_record`` calls for the same phone:
        exactly 1 allowed, 9 rejected with per_minute_exceeded + a TTL
        hint > 0 so the API can return ``Retry-After``.
        """
        rl = SMSRateLimiter(fake_redis)

        decisions = await asyncio.gather(
            *[rl.check_and_record(self.PHONE) for _ in range(10)]
        )

        allowed = [d for d in decisions if d.allowed]
        rejected = [d for d in decisions if not d.allowed]

        assert len(allowed) == 1, (
            f"Expected exactly 1/10 concurrent OTP sends to win, got "
            f"{len(allowed)}. Race condition allows OTP flooding."
        )
        assert len(rejected) == 9
        for d in rejected:
            assert d.reason == "per_minute_exceeded", (
                f"Wrong rejection reason: {d.reason!r}"
            )
            assert d.retry_after_seconds > 0, (
                "Caller needs a positive retry_after hint to surface "
                "Retry-After to the client."
            )

    async def test_counter_resets_after_window(self, fake_redis, monkeypatch):
        """After the 60s per-minute window expires, a fresh send must
        be allowed. Verified by monkeypatching ``time.time`` (FakeRedis
        does not enforce TTL on its own).
        """
        import time as _time
        from app.services.providers.sms import rate_limit as rl_mod

        clock = {"now": 1_000_000.0}
        monkeypatch.setattr(rl_mod.time, "time", lambda: clock["now"])

        rl = SMSRateLimiter(fake_redis)

        first = await rl.check_and_record(self.PHONE)
        assert first.allowed, "first send must be allowed"

        # Immediate retry within the window is rejected.
        second = await rl.check_and_record(self.PHONE)
        assert not second.allowed
        assert second.reason == "per_minute_exceeded"

        # Simulate the 60s window passing. We have to drop the old
        # per-minute key from FakeRedis ourselves because the in-test
        # backend doesn't enforce TTL - that mirrors what real Redis
        # would do automatically when the key expires.
        await fake_redis.delete(rl.KEY_MINUTE.format(phone=self.PHONE))
        clock["now"] += 61.0

        third = await rl.check_and_record(self.PHONE)
        assert third.allowed, (
            "After 60s window the per-minute counter must reset; got "
            f"reason={third.reason!r}"
        )

    async def test_inproc_fallback_also_safe_under_concurrency(self):
        """The Redis-less in-process fallback (single-worker dev,
        unit tests) must enforce the same single-winner contract."""
        rl = SMSRateLimiter(None)  # forces _inproc_check path

        decisions = await asyncio.gather(
            *[rl.check_and_record("13900000099") for _ in range(8)]
        )
        allowed = sum(1 for d in decisions if d.allowed)
        assert allowed == 1, (
            f"In-process fallback let {allowed}/8 concurrent sends through"
        )


# ---------------------------------------------------------------------------
# (b) Same IP, different phones, concurrent -> slowapi per-IP limiter caps it
# ---------------------------------------------------------------------------

class TestSameIPDifferentPhonesConcurrent:
    """``@limiter.limit("5/minute")`` on /send-otp must hold even when
    the 6th+ requests arrive on the same loop tick from different
    phones.
    """

    async def test_six_th_request_from_same_ip_returns_429(self, client):
        # 10 distinct phones, all from the synthetic ASGITransport IP.
        phones = [f"138000010{i:02d}" for i in range(10)]

        async def send(phone: str):
            return await client.post(
                "/api/v1/auth/send-otp", json={"phone": phone}
            )

        responses = await asyncio.gather(*[send(p) for p in phones])

        statuses = [r.status_code for r in responses]
        successes = sum(1 for s in statuses if s == 200)
        too_many = sum(1 for s in statuses if s == 429)

        # slowapi default is 5/minute on this endpoint.
        assert successes == 5, (
            f"Per-IP limit should cap at 5/min; got {successes} successes. "
            f"All statuses: {statuses}"
        )
        assert too_many == 5, (
            f"Expected 5 rejections with HTTP 429, got {too_many}. "
            f"All statuses: {statuses}"
        )

        # The 429 envelope from slowapi should mention the limit.
        rejected_bodies = [
            r.json() for r in responses if r.status_code == 429
        ]
        assert rejected_bodies, "no 429 bodies to inspect"
        # slowapi default body has an "error" key with the limit text.
        sample = rejected_bodies[0]
        body_str = str(sample).lower()
        assert "5" in body_str and (
            "minute" in body_str or "rate" in body_str
        ), f"Unexpected 429 body shape: {sample!r}"


# ---------------------------------------------------------------------------
# (c) Different phones AND different IPs, concurrent -> all must pass
# ---------------------------------------------------------------------------

class TestDifferentPhonesDifferentIPsConcurrent:
    """Control case: when neither the per-phone nor the per-IP key
    collides, no request must be throttled. Catches the regression
    where a future refactor accidentally makes the limiter key global.
    """

    async def test_all_unique_pairs_succeed(self, client, monkeypatch):
        # Vary slowapi's key per request by assigning each phone its
        # own synthetic IP via a counter-based key_func override.
        # (httpx's ASGITransport pins request.client.host, so we can't
        # vary it through the request itself.)
        #
        # slowapi snapshots the Limiter's ``key_func`` into each
        # registered ``Limit`` at decoration time, so mutating
        # ``ip_limiter._key_func`` here would have no effect - we
        # have to swap ``key_func`` on the per-route Limit object too.
        ip_iter: Iterator[str] = (f"10.0.0.{i}" for i in itertools.count(1))
        ip_for_phone: dict[str, str] = {}

        def keyed_by_phone(request):
            # Synchronous: slowapi invokes key_func without await.
            try:
                import json
                raw = getattr(request, "_body", None) or b"{}"
                phone = json.loads(bytes(raw)).get("phone", "anon")
            except Exception:
                phone = "anon"
            if phone not in ip_for_phone:
                ip_for_phone[phone] = next(ip_iter)
            return ip_for_phone[phone]

        # Patch every Limit registered for the send-otp route.
        route_limits = ip_limiter._route_limits.get(
            "app.api.v1.auth.send_otp", []
        )
        assert route_limits, (
            "send_otp route has no registered slowapi Limit; "
            "did the @limiter.limit decorator move?"
        )
        for lim in route_limits:
            monkeypatch.setattr(lim, "key_func", keyed_by_phone)
        # Also patch the limiter-level default so nothing falls back
        # to the IP-based key.
        monkeypatch.setattr(ip_limiter, "_key_func", keyed_by_phone)

        phones = [f"137000020{i:02d}" for i in range(10)]

        async def send(phone: str):
            return await client.post(
                "/api/v1/auth/send-otp", json={"phone": phone}
            )

        responses = await asyncio.gather(*[send(p) for p in phones])
        statuses = [r.status_code for r in responses]

        assert all(s == 200 for s in statuses), (
            "Every (unique phone, unique IP) request must succeed; "
            f"got statuses={statuses}. Some collision in the limit key?"
        )
        # Sanity: each phone really did get a distinct synthetic IP.
        assert len(set(ip_for_phone.values())) == len(phones)
