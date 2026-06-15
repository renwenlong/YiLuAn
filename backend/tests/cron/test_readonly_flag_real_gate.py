"""ADR-0053 §AC#6 — Read-only flag real T-7 cron gate unit tests.

AC#6 4 场景:
  1. 全绿 GO — 3 metric 都有数, SLA/drop/complaint 都在阈内
  2. metric 缺失 NOGO — token_revoke query 返回 None
  3. SLA breach NOGO — relogin SLA 跌破 99%
  4. customer complaint breach NOGO — complaint rate ≥ 0.1%

每个场景也断 prometheus counter 是否 +1 (`readonly_real_gate_run_total{result}`
+ `readonly_real_gate_nogo_total{reason}`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.cron.readonly_flag_real_gate import (
    PROMQL_RELOGIN_SLA_7D,
    PROMQL_SESSION_DROP_RATE_7D,
    PROMQL_TOKEN_REVOKE_7D,
    check_readonly_flag_real_gate,
)
from app.observability.readonly_real_gate_metrics import (
    READONLY_REAL_GATE_NOGO_TOTAL,
    READONLY_REAL_GATE_RUN_TOTAL,
)
from app.services.readonly_complaint_rate_store import (
    ComplaintRateStore,
    reset_default_store_for_tests,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers — build a fake prometheus HTTP layer
# ---------------------------------------------------------------------------


def _make_prom_payload(value: float | None) -> dict[str, Any]:
    """Build a fake prometheus /api/v1/query 'instant' response payload."""
    if value is None:
        return {"status": "success", "data": {"resultType": "vector", "result": []}}
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {
                    "metric": {},
                    "value": [1717400000.0, str(value)],
                }
            ],
        },
    }


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeAsyncClient:
    """Replaces ``httpx.AsyncClient`` for the cron under test.

    Caller passes a mapping ``{promql: scalar_or_None}``. Each GET to
    ``/api/v1/query`` returns a stub matching the requested query.
    """

    def __init__(self, query_to_value: dict[str, float | None], **kw: Any) -> None:
        self._map = query_to_value

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    async def get(self, url: str, *, params: dict[str, str]) -> _FakeResponse:
        query = params["query"]
        if query not in self._map:
            raise AssertionError(f"unexpected promql in test: {query}")
        return _FakeResponse(_make_prom_payload(self._map[query]))


def _factory(query_to_value: dict[str, float | None]):
    """Return a callable signature compatible with ``http_client_factory``."""

    def _make(**kw: Any) -> _FakeAsyncClient:
        return _FakeAsyncClient(query_to_value)

    return _make


def _counter_value(counter: Any, **labels: str) -> float:
    """Read a Counter labelset value (works with `prometheus_client` Counter)."""
    metric = counter.labels(**labels)
    # Counter._value._value is the raw float
    return metric._value.get()


NOW = datetime(2026, 6, 14, 2, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_store() -> None:
    """Each test starts with a clean in-proc complaint rate store."""
    reset_default_store_for_tests()
    yield
    reset_default_store_for_tests()


# ---------------------------------------------------------------------------
# AC#6 Scenario 1: 全绿 GO
# ---------------------------------------------------------------------------


async def test_gate_all_green_returns_go() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: 42.0,  # >0 = 数据存在
        PROMQL_RELOGIN_SLA_7D: 99.7,  # ≥99 = 通过
        PROMQL_SESSION_DROP_RATE_7D: 0.12,  # <0.5 = 通过
    }
    store = ComplaintRateStore(redis_client=None)
    await store.record_rate(0.03)  # <0.1% 通过

    before_run = _counter_value(READONLY_REAL_GATE_RUN_TOTAL, result="GO")

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "GO"
    assert result["reason"] == ""
    assert result["token_revoke_7d"] == 42.0
    assert result["relogin_sla_pct"] == 99.7
    assert result["session_drop_rate_pct"] == 0.12
    assert abs(result["customer_complaint_rate_pct"] - 0.03) < 1e-9
    assert all(result["metric_deployed"].values())
    assert result["ran_at"] == NOW.isoformat()

    after_run = _counter_value(READONLY_REAL_GATE_RUN_TOTAL, result="GO")
    assert after_run - before_run == 1.0


# ---------------------------------------------------------------------------
# AC#6 Scenario 2: metric 缺失 NOGO
# ---------------------------------------------------------------------------


async def test_gate_metric_missing_returns_nogo() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: None,  # 缺失 = NOGO
        PROMQL_RELOGIN_SLA_7D: 99.7,
        PROMQL_SESSION_DROP_RATE_7D: 0.12,
    }
    store = ComplaintRateStore(redis_client=None)
    await store.record_rate(0.03)

    before = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="metric_missing")
    before_run = _counter_value(READONLY_REAL_GATE_RUN_TOTAL, result="NOGO")

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "NOGO"
    assert "metric_missing" in result["reason"]
    assert "user_token_revoke_total" in result["reason"]
    assert result["metric_deployed"]["user_token_revoke_total"] is False
    assert result["metric_deployed"]["user_relogin_sla"] is True

    after = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="metric_missing")
    assert after - before == 1.0
    after_run = _counter_value(READONLY_REAL_GATE_RUN_TOTAL, result="NOGO")
    assert after_run - before_run == 1.0


# ---------------------------------------------------------------------------
# AC#6 Scenario 3: SLA breach NOGO
# ---------------------------------------------------------------------------


async def test_gate_relogin_sla_breach_returns_nogo() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: 100.0,
        PROMQL_RELOGIN_SLA_7D: 97.5,  # <99 = breach
        PROMQL_SESSION_DROP_RATE_7D: 0.1,
    }
    store = ComplaintRateStore(redis_client=None)
    await store.record_rate(0.02)

    before = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="relogin_sla_breach")

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "NOGO"
    assert "relogin_sla_breach" in result["reason"]
    assert result["relogin_sla_pct"] == 97.5

    after = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="relogin_sla_breach")
    assert after - before == 1.0


# ---------------------------------------------------------------------------
# AC#6 Scenario 4: customer complaint breach NOGO
# ---------------------------------------------------------------------------


async def test_gate_complaint_rate_breach_returns_nogo() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: 100.0,
        PROMQL_RELOGIN_SLA_7D: 99.9,
        PROMQL_SESSION_DROP_RATE_7D: 0.05,
    }
    store = ComplaintRateStore(redis_client=None)
    await store.record_rate(0.25)  # ≥0.1 = breach

    before = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="complaint_rate_breach")

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "NOGO"
    assert "complaint_rate_breach" in result["reason"]
    assert abs(result["customer_complaint_rate_pct"] - 0.25) < 1e-9

    after = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="complaint_rate_breach")
    assert after - before == 1.0


# ---------------------------------------------------------------------------
# Bonus coverage: 多原因 NOGO 触发多个 reason counter
# ---------------------------------------------------------------------------


async def test_gate_multiple_breaches_records_each_reason() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: 100.0,
        PROMQL_RELOGIN_SLA_7D: 90.0,  # SLA breach
        PROMQL_SESSION_DROP_RATE_7D: 2.5,  # drop breach
    }
    store = ComplaintRateStore(redis_client=None)
    await store.record_rate(5.0)  # complaint breach

    before_sla = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="relogin_sla_breach")
    before_drop = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="session_drop_breach")
    before_complaint = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason="complaint_rate_breach")

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "NOGO"
    for tag in ("relogin_sla_breach", "session_drop_breach", "complaint_rate_breach"):
        assert tag in result["reason"]
        after = _counter_value(READONLY_REAL_GATE_NOGO_TOTAL, reason=tag)
        before_map = {
            "relogin_sla_breach": before_sla,
            "session_drop_breach": before_drop,
            "complaint_rate_breach": before_complaint,
        }
        assert after - before_map[tag] == 1.0


# ---------------------------------------------------------------------------
# Bonus: complaint rate 未注入 (None) 走 grace 不阻 GO
# ---------------------------------------------------------------------------


async def test_gate_complaint_not_injected_does_not_block_go() -> None:
    qmap = {
        PROMQL_TOKEN_REVOKE_7D: 10.0,
        PROMQL_RELOGIN_SLA_7D: 99.5,
        PROMQL_SESSION_DROP_RATE_7D: 0.1,
    }
    # store has NO samples → get_rolling_average returns None
    store = ComplaintRateStore(redis_client=None)

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=_factory(qmap),
        complaint_rate_store=store,
    )

    assert result["go_no_go"] == "GO"
    assert result["customer_complaint_rate_pct"] is None


# ---------------------------------------------------------------------------
# Bonus: prometheus HTTP error returns None (treated as metric_missing)
# ---------------------------------------------------------------------------


async def test_gate_prometheus_unreachable_treats_as_metric_missing() -> None:
    class _BrokenClient:
        async def __aenter__(self) -> "_BrokenClient":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def get(self, url: str, *, params: dict[str, str]) -> _FakeResponse:
            import httpx

            raise httpx.ConnectError("connection refused")

    def factory(**kw: Any) -> _BrokenClient:
        return _BrokenClient()

    result = await check_readonly_flag_real_gate(
        prometheus_url="http://stub:9090",
        now_fn=lambda: NOW,
        http_client_factory=factory,
        complaint_rate_store=ComplaintRateStore(redis_client=None),
    )

    assert result["go_no_go"] == "NOGO"
    assert "metric_missing" in result["reason"]
    assert all(v is False for v in result["metric_deployed"].values())
