"""Tests for the unified outbound reliability decorator (ADR-0026 + ADR-0026r1).

W19-P0-04 / S2-DEV-007 scope:
- B1: half-open requires N consecutive successes to CLOSE; any single
  failure re-OPENs.
- B2: httpx 4xx → NonRetryable + record_success (no CB poison);
       httpx 5xx / RequestError → Retryable + record_failure.
- B3: CB-OPEN at attempt start raises immediately, no spurious record_failure,
      no extra attempt.
- IDLE: long quiet period auto-resets failure_count.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.utils.outbound import (
    CircuitBreaker,
    NonRetryableError,
    RetryableError,
    _get_circuit_breaker,
    classify_httpx_exception,
    outbound_call,
    reset_circuit_breakers,
)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


# ---------------------------------------------------------------------------
# Existing baseline behaviours (kept from original suite)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_timeout_retries_then_raises():
    call_count = 0

    @outbound_call(
        provider="test_to",
        timeout=0.01,
        max_retries=2,
        backoff_base=0.001,
        backoff_factor=1,
    )
    async def slow_fn():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(10)

    with pytest.raises(RetryableError, match="failed after 3 retries"):
        await slow_fn()
    assert call_count == 3


@pytest.mark.asyncio
async def test_retryable_error_then_success():
    call_count = 0

    @outbound_call(
        provider="test_re",
        timeout=1,
        max_retries=2,
        backoff_base=0.001,
        backoff_factor=1,
    )
    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RetryableError("5xx")
        return "ok"

    assert await flaky_fn() == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_non_retryable_no_retry():
    call_count = 0

    @outbound_call(
        provider="test_nr",
        timeout=1,
        max_retries=2,
        backoff_base=0.001,
        backoff_factor=1,
    )
    async def bad_request_fn():
        nonlocal call_count
        call_count += 1
        raise NonRetryableError("4xx bad request")

    with pytest.raises(NonRetryableError):
        await bad_request_fn()
    assert call_count == 1


# ---------------------------------------------------------------------------
# B1 — half-open N consecutive successes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    @outbound_call(
        provider="b1_open",
        timeout=1,
        max_retries=0,
        circuit_threshold=3,
        circuit_timeout=60,
    )
    async def failing_fn():
        raise RetryableError("fail")

    for _ in range(3):
        with pytest.raises(RetryableError):
            await failing_fn()
    cb = _get_circuit_breaker("b1_open", 3, 60)
    assert cb.state == CircuitBreaker.OPEN


@pytest.mark.asyncio
async def test_half_open_n_consecutive_successes_closes():
    """B1: HALF_OPEN -> CLOSED only after N=3 consecutive successes."""
    state = {"calls": 0, "fail_first_n": 2}

    @outbound_call(
        provider="b1_recover",
        timeout=1,
        max_retries=0,
        circuit_threshold=2,
        circuit_timeout=0.05,
        half_open_success_threshold=3,
    )
    async def fn():
        state["calls"] += 1
        if state["calls"] <= state["fail_first_n"]:
            raise RetryableError("fail")
        return "ok"

    for _ in range(2):
        with pytest.raises(RetryableError):
            await fn()

    cb = _get_circuit_breaker("b1_recover", 2, 0.05)
    assert cb.state == CircuitBreaker.OPEN

    await asyncio.sleep(0.15)  # cross open->half-open window

    # First probe: HALF_OPEN -> still half-open after 1 success
    assert await fn() == "ok"
    assert cb.state == CircuitBreaker.HALF_OPEN
    assert cb.half_open_success_count == 1

    # Second success — still half-open (need 3)
    assert await fn() == "ok"
    assert cb.state == CircuitBreaker.HALF_OPEN
    assert cb.half_open_success_count == 2

    # Third success — now CLOSED
    assert await fn() == "ok"
    assert cb.state == CircuitBreaker.CLOSED
    assert cb.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_single_failure_reopens():
    """B1: any failure in HALF_OPEN immediately re-OPENs, resets success counter."""

    @outbound_call(
        provider="b1_reopen",
        timeout=1,
        max_retries=0,
        circuit_threshold=2,
        circuit_timeout=0.05,
        half_open_success_threshold=3,
    )
    async def fail_fn():
        raise RetryableError("still bad")

    # Trip the breaker
    for _ in range(2):
        with pytest.raises(RetryableError):
            await fail_fn()

    cb = _get_circuit_breaker("b1_reopen", 2, 0.05)
    assert cb.state == CircuitBreaker.OPEN

    await asyncio.sleep(0.15)
    # Half-open probe fails -> re-open immediately
    with pytest.raises(RetryableError):
        await fail_fn()
    assert cb.state == CircuitBreaker.OPEN
    assert cb.half_open_success_count == 0


@pytest.mark.asyncio
async def test_half_open_n_minus_one_then_fail_does_not_close():
    """B1: N-1 successes followed by failure does not CLOSE."""

    state = {"i": 0}
    seq = ["ok", "ok", "fail"]  # 2 wins then 1 fail at N=3

    @outbound_call(
        provider="b1_partial",
        timeout=1,
        max_retries=0,
        circuit_threshold=2,
        circuit_timeout=0.05,
        half_open_success_threshold=3,
    )
    async def fn():
        i = state["i"]
        state["i"] += 1
        if i < 2:  # initial 2 fails to trip
            raise RetryableError("trip")
        idx = i - 2
        if seq[idx] == "fail":
            raise RetryableError("half-open flake")
        return "ok"

    for _ in range(2):
        with pytest.raises(RetryableError):
            await fn()
    cb = _get_circuit_breaker("b1_partial", 2, 0.05)
    assert cb.state == CircuitBreaker.OPEN

    await asyncio.sleep(0.15)
    assert await fn() == "ok"
    assert await fn() == "ok"
    assert cb.state == CircuitBreaker.HALF_OPEN

    with pytest.raises(RetryableError):
        await fn()
    assert cb.state == CircuitBreaker.OPEN


# ---------------------------------------------------------------------------
# B2 — httpx classifier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_httpx_4xx_classified_non_retryable_and_does_not_poison_cb():
    httpx = pytest.importorskip("httpx")

    cb = _get_circuit_breaker("b2_4xx", 3, 60)
    cb.failure_count = 0

    @outbound_call(
        provider="b2_4xx",
        timeout=1,
        max_retries=2,
        backoff_base=0.001,
        backoff_factor=1,
        circuit_threshold=3,
        circuit_timeout=60,
    )
    async def fn():
        resp = httpx.Response(400, request=httpx.Request("POST", "http://x"))
        raise classify_httpx_exception(
            httpx.HTTPStatusError("400", request=resp.request, response=resp)
        )

    with pytest.raises(NonRetryableError):
        await fn()
    assert cb.failure_count == 0  # CB not poisoned by 4xx
    assert cb.state == CircuitBreaker.CLOSED


@pytest.mark.asyncio
async def test_httpx_5xx_classified_retryable_and_increments_failures():
    httpx = pytest.importorskip("httpx")

    @outbound_call(
        provider="b2_5xx",
        timeout=1,
        max_retries=0,
        circuit_threshold=10,
    )
    async def fn():
        resp = httpx.Response(503, request=httpx.Request("POST", "http://x"))
        raise classify_httpx_exception(
            httpx.HTTPStatusError("503", request=resp.request, response=resp)
        )

    with pytest.raises(RetryableError):
        await fn()
    cb = _get_circuit_breaker("b2_5xx", 10, 60)
    assert cb.failure_count == 1


@pytest.mark.asyncio
async def test_httpx_request_error_classified_retryable():
    httpx = pytest.importorskip("httpx")

    @outbound_call(
        provider="b2_neterr",
        timeout=1,
        max_retries=1,
        backoff_base=0.001,
        backoff_factor=1,
    )
    async def fn():
        raise classify_httpx_exception(
            httpx.ConnectError("connect refused", request=httpx.Request("POST", "http://x"))
        )

    with pytest.raises(RetryableError):
        await fn()


def test_httpx_429_and_408_classified_retryable():
    httpx = pytest.importorskip("httpx")
    for status in (408, 429):
        resp = httpx.Response(status, request=httpx.Request("GET", "http://x"))
        classified = classify_httpx_exception(
            httpx.HTTPStatusError(str(status), request=resp.request, response=resp)
        )
        assert isinstance(classified, RetryableError), f"{status} should be Retryable"


# ---------------------------------------------------------------------------
# B3 — CB-OPEN short-circuit, no spurious work
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_circuit_open_short_circuits_call_count_unchanged():
    """B3: When CB is OPEN, fn body must not run, retry loop must not re-enter."""
    call_count = 0

    @outbound_call(
        provider="b3_short",
        timeout=1,
        max_retries=3,  # 4 attempts max if not short-circuited
        circuit_threshold=2,
        circuit_timeout=60,
        backoff_base=0.001,
        backoff_factor=1,
    )
    async def fn():
        nonlocal call_count
        call_count += 1
        raise RetryableError("fail")

    # Trip
    for _ in range(2):
        with pytest.raises(RetryableError):
            await fn()
    assert call_count == 2

    # Now CB is OPEN; next invocation must hit allow_request=False on the
    # very first attempt, raise immediately, fn body must not be entered.
    cb = _get_circuit_breaker("b3_short", 2, 60)
    failures_before = cb.failure_count

    with pytest.raises(RetryableError, match="Circuit breaker open"):
        await fn()

    assert call_count == 2  # body not entered
    assert cb.failure_count == failures_before  # no spurious record_failure


# ---------------------------------------------------------------------------
# IDLE auto-reset
# ---------------------------------------------------------------------------


def test_idle_reset_clears_failure_count_after_quiet_period():
    cb = CircuitBreaker(
        threshold=5, timeout=60, half_open_success_threshold=3,
        idle_reset_seconds=0.05,
    )
    cb.record_failure()
    cb.record_failure()
    assert cb.failure_count == 2

    # Simulate idle period
    cb._last_activity_at = time.monotonic() - 1.0
    assert cb.allow_request() is True
    assert cb.failure_count == 0  # auto-reset


# ---------------------------------------------------------------------------
# Backward-compat: outbound_call without new kwargs still works
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_backward_compat_no_new_kwargs():
    @outbound_call(provider="compat", timeout=1, max_retries=0)
    async def fn():
        return 42

    assert await fn() == 42
