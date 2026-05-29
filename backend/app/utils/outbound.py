"""
Unified outbound reliability decorator (ADR-0026 + ADR-0026r1).

Provides timeout, exponential-backoff retry, and circuit-breaker semantics
for all external API calls (payment, SMS, Redis pub/sub, OSS, AI providers).

ADR-0026r1 / W19-P0-04 / S2-DEV-007 fixes:
- B1: half-open requires N consecutive successes before transitioning to
  CLOSED (default N=3). Any single failure in half-open re-opens.
- B2: ``classify_httpx_exception`` helper translates ``httpx`` errors into
  the Retryable / NonRetryable taxonomy: 4xx → NonRetryable + record_success
  (do not poison CB); 5xx → record_failure + retry; RequestError →
  record_failure + retry.
- B3: When the CB is OPEN at the *start* of an attempt the decorator
  raises immediately without entering the call body — no spurious
  record_failure, no `next attempt` loop bumping retries.
- IDLE: If a provider sees no traffic for ``idle_reset_seconds`` (default
  10× ``circuit_timeout``) the breaker's failure_count is auto-reset so the
  first request after a quiet period does not inherit stale failures.
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
    from prometheus_client import REGISTRY, Counter, Gauge, Histogram

    def _gauge(name: str, doc: str, labels: list[str]) -> Gauge:
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is not None:
            return existing  # type: ignore[return-value]
        return Gauge(name, doc, labels)

    def _counter(name: str, doc: str, labels: list[str]) -> Counter:
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is not None:
            return existing  # type: ignore[return-value]
        return Counter(name, doc, labels)

    def _histogram(name: str, doc: str, labels: list[str]) -> Histogram:
        existing = REGISTRY._names_to_collectors.get(name)  # type: ignore[attr-defined]
        if existing is not None:
            return existing  # type: ignore[return-value]
        return Histogram(name, doc, labels)

    outbound_call_total = _counter(
        "outbound_call_total",
        "Total outbound calls",
        ["provider", "method", "outcome"],
    )
    outbound_call_duration_seconds = _histogram(
        "outbound_call_duration_seconds",
        "Outbound call duration",
        ["provider", "method"],
    )
    outbound_circuit_breaker_state = _gauge(
        "outbound_circuit_breaker_state",
        "Circuit breaker state (0=closed, 1=open, 0.5=half-open)",
        ["provider"],
    )
    outbound_circuit_state = _gauge(
        "outbound_circuit_state",
        "Alias for outbound_circuit_breaker_state — preferred metric name "
        "per ADR-0026r1 (0=closed, 1=open, 0.5=half-open).",
        ["provider"],
    )
    _HAS_PROMETHEUS = True
except ImportError:  # pragma: no cover
    _HAS_PROMETHEUS = False


# ---------------------------------------------------------------------------
# Error types
# ---------------------------------------------------------------------------


class RetryableError(Exception):
    """Error that should be retried (timeout, 5xx, network)."""


class NonRetryableError(Exception):
    """Error that must NOT be retried (4xx, business rejection)."""


# ---------------------------------------------------------------------------
# httpx exception classifier (ADR-0026r1 B2)
# ---------------------------------------------------------------------------


def classify_httpx_exception(exc: BaseException) -> Exception:
    """Translate a raw ``httpx`` exception into Retryable / NonRetryable.

    Callers wrapping ``httpx`` calls inside ``@outbound_call`` should do::

        try:
            resp = await client.post(...)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            raise classify_httpx_exception(e) from e

    Rules (B2):
    - ``httpx.HTTPStatusError`` 4xx → ``NonRetryableError`` (caller bug or
      legitimate business rejection; do not pollute the breaker).
    - ``httpx.HTTPStatusError`` 5xx / 408 / 429 → ``RetryableError``.
    - ``httpx.TimeoutException`` / ``httpx.RequestError`` → ``RetryableError``.
    - Anything else → return as-is (NonRetryable by default — caller can
      wrap in RetryableError if it knows better).
    """
    try:
        import httpx  # local import to keep this module httpx-optional
    except ImportError:  # pragma: no cover
        return exc if isinstance(exc, Exception) else RetryableError(str(exc))

    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (408, 429) or 500 <= status < 600:
            return RetryableError(f"httpx {status}: {exc}")
        # 4xx (other than 408/429) is a client-side problem; not the
        # upstream provider's fault, must not poison the CB.
        return NonRetryableError(f"httpx {status}: {exc}")

    if isinstance(exc, (httpx.TimeoutException, httpx.RequestError)):
        return RetryableError(f"httpx network: {exc}")

    return exc if isinstance(exc, Exception) else RetryableError(str(exc))


# ---------------------------------------------------------------------------
# Circuit breaker (per-provider singleton)
# ---------------------------------------------------------------------------


_circuit_breakers: dict[str, "CircuitBreaker"] = {}


class CircuitBreaker:
    """Async circuit breaker with N-consecutive-success half-open recovery.

    States:
      - CLOSED: requests flow through.
      - OPEN: requests rejected until ``timeout`` elapses.
      - HALF_OPEN: probes allowed; need ``half_open_success_threshold``
        consecutive successes to CLOSE; any failure re-OPENs.
    """

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(
        self,
        threshold: int,
        timeout: float,
        half_open_success_threshold: int = 3,
        idle_reset_seconds: float | None = None,
    ) -> None:
        self.threshold = threshold
        self.timeout = timeout
        self.half_open_success_threshold = max(1, half_open_success_threshold)
        # Auto-reset failure_count if no traffic for this long. Defaults to
        # 10× the CB open-timeout — long enough that a quiet provider isn't
        # punished by stale failures at the next request.
        self.idle_reset_seconds = (
            idle_reset_seconds
            if idle_reset_seconds is not None
            else max(60.0, timeout * 10.0)
        )

        self.state = self.CLOSED
        self.failure_count = 0
        self.half_open_success_count = 0
        self._opened_at: float = 0.0
        self._last_activity_at: float = time.monotonic()

    # -- transitions ---------------------------------------------------------

    def record_success(self) -> None:
        self._last_activity_at = time.monotonic()
        if self.state == self.HALF_OPEN:
            self.half_open_success_count += 1
            if self.half_open_success_count >= self.half_open_success_threshold:
                self.state = self.CLOSED
                self.failure_count = 0
                self.half_open_success_count = 0
            return
        # CLOSED success: clear any accumulated failures.
        self.failure_count = 0
        self.half_open_success_count = 0

    def record_failure(self) -> None:
        now = time.monotonic()
        self._last_activity_at = now

        # Any failure during HALF_OPEN immediately re-opens and resets the
        # success counter.
        if self.state == self.HALF_OPEN:
            self.state = self.OPEN
            self._opened_at = now
            self.failure_count = self.threshold  # remain tripped
            self.half_open_success_count = 0
            return

        self.failure_count += 1
        if self.failure_count >= self.threshold:
            self.state = self.OPEN
            self._opened_at = now
            self.half_open_success_count = 0

    # -- gating --------------------------------------------------------------

    def allow_request(self) -> bool:
        now = time.monotonic()

        # IDLE auto-reset: long quiet period clears stale failure_count to
        # avoid the "midnight first request kills us" failure mode.
        if (
            self.state == self.CLOSED
            and self.failure_count > 0
            and now - self._last_activity_at >= self.idle_reset_seconds
        ):
            self.failure_count = 0

        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            if now - self._opened_at >= self.timeout:
                self.state = self.HALF_OPEN
                self.half_open_success_count = 0
                return True
            return False
        # HALF_OPEN: allow probes (caller serialises naturally via await).
        return True


def _get_circuit_breaker(
    provider: str,
    threshold: int,
    timeout: float,
    half_open_success_threshold: int = 3,
    idle_reset_seconds: float | None = None,
) -> CircuitBreaker:
    if provider not in _circuit_breakers:
        _circuit_breakers[provider] = CircuitBreaker(
            threshold,
            timeout,
            half_open_success_threshold=half_open_success_threshold,
            idle_reset_seconds=idle_reset_seconds,
        )
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
    half_open_success_threshold: int = 3,
    idle_reset_seconds: float | None = None,
) -> Callable:
    """Decorator adding timeout / retry / circuit-breaker to an async call.

    Parameters
    ----------
    half_open_success_threshold
        Number of consecutive successes needed in HALF_OPEN to fully CLOSE
        the breaker. Default 3 (ADR-0026r1 B1). Any failure in HALF_OPEN
        immediately re-OPENs.
    idle_reset_seconds
        If the provider sees no traffic for this many seconds while CLOSED,
        the accumulated ``failure_count`` is auto-reset on the next call.
        Defaults to ``max(60, circuit_timeout * 10)``.
    """

    def decorator(fn: Callable) -> Callable:
        method_name = fn.__name__

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            cb = _get_circuit_breaker(
                provider,
                circuit_threshold,
                circuit_timeout,
                half_open_success_threshold=half_open_success_threshold,
                idle_reset_seconds=idle_reset_seconds,
            )
            start = time.monotonic()
            retries = 0
            last_exc: Exception | None = None

            for attempt in range(max_retries + 1):
                # B3: CB-OPEN short-circuit — do NOT enter call body, do
                # NOT call record_failure, do NOT loop into next attempt.
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
                    # B2: 4xx is caller/business error — record success so
                    # the breaker is not poisoned by client-side bugs.
                    cb.record_success()
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
        outbound_circuit_state.labels(provider=provider).set(state_val)
