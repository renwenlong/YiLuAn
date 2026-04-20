"""
Unified outbound reliability decorator (ADR-0026).

Provides timeout, exponential-backoff retry, and circuit-breaker semantics
for all external API calls (payment, SMS, etc.).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prometheus metrics (lazy — only created when prometheus_client is installed)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import Counter, Gauge, Histogram

    outbound_call_total = Counter(
        "outbound_call_total",
        "Total outbound calls",
        ["provider", "method", "outcome"],
    )
    outbound_call_duration_seconds = Histogram(
        "outbound_call_duration_seconds",
        "Outbound call duration",
        ["provider", "method"],
    )
    outbound_circuit_breaker_state = Gauge(
        "outbound_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 0.5=half-open)",
        ["provider"],
    )
    _HAS_PROMETHEUS = True
except ImportError:  # pragma: no cover
    _HAS_PROMETHEUS = False


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class RetryableError(Exception):
    """Error that should be retried (timeout, 5xx, 429)."""


class NonRetryableError(Exception):
    """Error that must NOT be retried (4xx, business rejection)."""


# ---------------------------------------------------------------------------
# Circuit breaker (per-provider singleton)
# ---------------------------------------------------------------------------

_circuit_breakers: dict[str, CircuitBreaker] = {}


class CircuitBreaker:
    """Minimal async circuit breaker."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(self, threshold: int, timeout: float) -> None:
        self.threshold = threshold
        self.timeout = timeout
        self.state = self.CLOSED
        self.failure_count = 0
        self._opened_at: float = 0.0

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = self.CLOSED

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.state = self.OPEN
            self._opened_at = time.monotonic()

    def allow_request(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if time.monotonic() - self._opened_at >= self.timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        # half-open: allow one probe
        return True


def _get_circuit_breaker(
    provider: str, threshold: int, timeout: float
) -> CircuitBreaker:
    if provider not in _circuit_breakers:
        _circuit_breakers[provider] = CircuitBreaker(threshold, timeout)
    return _circuit_breakers[provider]


def reset_circuit_breakers() -> None:
    """Reset all circuit breakers — useful in tests."""
    _circuit_breakers.clear()


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def outbound_call(
    provider: str,
    timeout: float = 5.0,
    max_retries: int = 2,
    backoff_base: float = 0.2,
    backoff_factor: float = 4,
    circuit_threshold: int = 5,
    circuit_timeout: float = 60,
) -> Callable:
    """Decorator adding timeout / retry / circuit-breaker to an async call."""

    def decorator(fn: Callable) -> Callable:
        method_name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = _get_circuit_breaker(provider, circuit_threshold, circuit_timeout)
            start = time.monotonic()
            retries = 0
            last_exc: Exception | None = None

            for attempt in range(max_retries + 1):
                # Circuit breaker check
                if not cb.allow_request():
                    duration_ms = (time.monotonic() - start) * 1000
                    _log_and_record(
                        provider, method_name, duration_ms, retries,
                        cb.state, "circuit_open",
                    )
                    raise RetryableError(
                        f"Circuit breaker open for {provider}"
                    )

                try:
                    result = await asyncio.wait_for(
                        fn(*args, **kwargs), timeout=timeout
                    )
                    cb.record_success()
                    duration_ms = (time.monotonic() - start) * 1000
                    _log_and_record(
                        provider, method_name, duration_ms, retries,
                        cb.state, "success",
                    )
                    return result

                except NonRetryableError:
                    duration_ms = (time.monotonic() - start) * 1000
                    _log_and_record(
                        provider, method_name, duration_ms, retries,
                        cb.state, "non_retryable",
                    )
                    raise

                except (asyncio.TimeoutError, RetryableError) as exc:
                    last_exc = exc
                    cb.record_failure()
                    retries = attempt + 1

                    if attempt < max_retries:
                        delay = backoff_base * (backoff_factor ** attempt)
                        await asyncio.sleep(delay)

            # All retries exhausted
            duration_ms = (time.monotonic() - start) * 1000
            _log_and_record(
                provider, method_name, duration_ms, retries,
                cb.state, "retry_exhausted",
            )
            raise RetryableError(
                f"{provider}.{method_name} failed after {retries} retries"
            ) from last_exc

        return wrapper

    return decorator


def _log_and_record(
    provider: str,
    method: str,
    duration_ms: float,
    retries: int,
    circuit_state: str,
    outcome: str,
) -> None:
    logger.info(
        "outbound_call provider=%s method=%s duration_ms=%.1f retries=%d "
        "circuit_state=%s outcome=%s",
        provider, method, duration_ms, retries, circuit_state, outcome,
    )
    if _HAS_PROMETHEUS:
        outbound_call_total.labels(
            provider=provider, method=method, outcome=outcome
        ).inc()
        outbound_call_duration_seconds.labels(
            provider=provider, method=method
        ).observe(duration_ms / 1000)
        state_val = {"closed": 0, "open": 1, "half-open": 0.5}.get(
            circuit_state, 0
        )
        outbound_circuit_breaker_state.labels(provider=provider).set(state_val)
