"""S2-DEV-012: @outbound_call(distributed=True) 集成单测

验证 decorator 参数透传 + 默认 False 行为不变（向后兼容）。
"""

from __future__ import annotations

import pytest

from app.utils.distributed_circuit_breaker import (
    DistributedCircuitBreaker,
    set_distributed_redis_client,
)
from app.utils.outbound import (
    CircuitBreaker,
    _circuit_breakers,
    outbound_call,
    reset_circuit_breakers,
)


@pytest.fixture(autouse=True)
def clean_state():
    reset_circuit_breakers()
    set_distributed_redis_client(None)
    yield
    reset_circuit_breakers()
    set_distributed_redis_client(None)


@pytest.mark.asyncio
async def test_outbound_call_distributed_false_uses_local_cb():
    """默认 distributed=False → 仍是 CircuitBreaker（不是 Distributed）"""

    @outbound_call(provider="test_local", circuit_threshold=2)
    async def fake_call() -> str:
        return "ok"

    await fake_call()
    cb = _circuit_breakers["test_local"]
    assert isinstance(cb, CircuitBreaker)
    assert not isinstance(cb, DistributedCircuitBreaker)


@pytest.mark.asyncio
async def test_outbound_call_distributed_true_uses_distributed_cb():
    """distributed=True → DistributedCircuitBreaker 实例"""

    @outbound_call(provider="test_distributed", circuit_threshold=2, distributed=True)
    async def fake_call() -> str:
        return "ok"

    await fake_call()
    cb = _circuit_breakers["test_distributed"]
    assert isinstance(cb, DistributedCircuitBreaker)
    # provider 字段正确传入
    assert cb.provider == "test_distributed"


@pytest.mark.asyncio
async def test_outbound_call_distributed_with_probe_lock_ttl_override():
    """probe_lock_ttl 显式覆盖"""

    @outbound_call(
        provider="test_ttl",
        circuit_threshold=2,
        distributed=True,
        probe_lock_ttl=12.5,
    )
    async def fake_call() -> str:
        return "ok"

    await fake_call()
    cb = _circuit_breakers["test_ttl"]
    assert isinstance(cb, DistributedCircuitBreaker)
    assert cb.probe_lock_ttl == 12.5


@pytest.mark.asyncio
async def test_distributed_cb_inherits_base_behavior_success_recording():
    """DistributedCircuitBreaker 继承 base record_success/record_failure"""

    @outbound_call(
        provider="test_inherit",
        circuit_threshold=2,
        distributed=True,
    )
    async def fake_call() -> str:
        return "ok"

    for _ in range(3):
        await fake_call()

    cb = _circuit_breakers["test_inherit"]
    # 多次成功 → 仍 CLOSED + failure_count=0
    assert cb.state == cb.CLOSED
    assert cb.failure_count == 0
