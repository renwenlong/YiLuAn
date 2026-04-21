"""Tests for the unified outbound reliability decorator (ADR-0026)."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from app.utils.outbound import (
    CircuitBreaker,
    NonRetryableError,
    RetryableError,
    _get_circuit_breaker,
    outbound_call,
    reset_circuit_breakers,
)


@pytest.fixture(autouse=True)
def _clean_breakers():
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


# 1. Timeout triggers RetryableError + retries to max_retries then raises
@pytest.mark.asyncio
async def test_timeout_retries_then_raises():
    call_count = 0

    @outbound_call(provider="test", timeout=0.01, max_retries=2, backoff_base=0.001, backoff_factor=1)
    async def slow_fn():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(10)  # will always timeout

    with pytest.raises(RetryableError, match="failed after 3 retries"):
        await slow_fn()

    assert call_count == 3  # initial + 2 retries


# 2. 5xx triggers retry, second attempt succeeds
@pytest.mark.asyncio
async def test_retryable_error_then_success():
    call_count = 0

    @outbound_call(provider="test", timeout=1, max_retries=2, backoff_base=0.001, backoff_factor=1)
    async def flaky_fn():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RetryableError("5xx")
        return "ok"

    result = await flaky_fn()
    assert result == "ok"
    assert call_count == 2


# 3. 4xx (NonRetryableError) does not retry
@pytest.mark.asyncio
async def test_non_retryable_no_retry():
    call_count = 0

    @outbound_call(provider="test", timeout=1, max_retries=2, backoff_base=0.001, backoff_factor=1)
    async def bad_request_fn():
        nonlocal call_count
        call_count += 1
        raise NonRetryableError("4xx bad request")

    with pytest.raises(NonRetryableError, match="4xx"):
        await bad_request_fn()

    assert call_count == 1  # no retry


# 4. Consecutive failures reach circuit_threshold → circuit opens
@pytest.mark.asyncio
async def test_circuit_opens_after_threshold():
    @outbound_call(
        provider="breaker_test",
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

    cb = _get_circuit_breaker("breaker_test", 3, 60)
    assert cb.state == CircuitBreaker.OPEN


# 5. Circuit open rejects calls immediately (no actual call)
@pytest.mark.asyncio
async def test_circuit_open_rejects():
    call_count = 0

    @outbound_call(
        provider="reject_test",
        timeout=1,
        max_retries=0,
        circuit_threshold=2,
        circuit_timeout=60,
    )
    async def fn():
        nonlocal call_count
        call_count += 1
        raise RetryableError("fail")

    # Trip the breaker
    for _ in range(2):
        with pytest.raises(RetryableError):
            await fn()

    assert call_count == 2

    # Next call should be rejected without invoking fn
    with pytest.raises(RetryableError, match="Circuit breaker open"):
        await fn()

    assert call_count == 2  # no new call made


# 6. Circuit open → half-open after timeout → success closes it
@pytest.mark.asyncio
async def test_circuit_half_open_recovers():
    call_count = 0

    @outbound_call(
        provider="recover_test",
        timeout=1,
        max_retries=0,
        circuit_threshold=2,
        circuit_timeout=0.05,  # 50ms for fast test
    )
    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RetryableError("fail")
        return "recovered"

    # Trip the breaker
    for _ in range(2):
        with pytest.raises(RetryableError):
            await fn()

    cb = _get_circuit_breaker("recover_test", 2, 0.05)
    assert cb.state == CircuitBreaker.OPEN

    # Wait for circuit_timeout.
    # Windows clock resolution ~15.6ms; sleep 0.15s ensures we cross
    # the 50ms circuit timeout reliably (covers worst-case granularity
    # plus ample margin so the test does not flake on Windows runners).
    await asyncio.sleep(0.15)

    # Should enter half-open and succeed
    result = await fn()
    assert result == "recovered"
    assert cb.state == CircuitBreaker.CLOSED
