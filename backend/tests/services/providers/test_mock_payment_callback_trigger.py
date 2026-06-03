"""S2-BUG-W001 修复验证：
MockPaymentProvider 在 MOCK_PAY_BASE_URL 设置时 fire-and-forget
触发 mock-pay-stub /__trigger-callback。
未设置时不发，单测/e2e 行为不变。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.services.providers.payment.base import OrderDTO
from app.services.providers.payment.mock import MockPaymentProvider


@pytest.mark.asyncio
async def test_create_order_returns_success_without_mock_pay_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无 MOCK_PAY_BASE_URL → 不触发 callback，行为不变。"""
    monkeypatch.delenv("MOCK_PAY_BASE_URL", raising=False)
    provider = MockPaymentProvider()

    with patch("httpx.AsyncClient") as mock_client:
        result = await provider.create_order(
            OrderDTO(order_number="YLA2026060300001", amount_yuan=299)
        )

    assert result["status"] == "success"
    assert result["trade_no"].startswith("MOCK_")
    mock_client.assert_not_called()


@pytest.mark.asyncio
async def test_create_order_triggers_mock_pay_stub_when_url_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """设置 MOCK_PAY_BASE_URL → fire-and-forget POST /__trigger-callback."""
    monkeypatch.setenv("MOCK_PAY_BASE_URL", "http://mock-pay-stub:8001")
    provider = MockPaymentProvider()

    captured: dict[str, Any] = {}

    class _FakeResp:
        status_code = 200
        text = "{}"

    class _FakeClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self) -> "_FakeClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResp:
            captured["url"] = url
            captured["payload"] = json
            return _FakeResp()

    with patch("app.services.providers.payment.mock.httpx.AsyncClient", _FakeClient):
        result = await provider.create_order(
            OrderDTO(order_number="YLA2026060300002", amount_yuan=199)
        )
        # 等 fire-and-forget 的 background task 完成
        await asyncio.sleep(0.05)

    assert result["status"] == "success"
    assert captured.get("url") == "http://mock-pay-stub:8001/__trigger-callback"
    payload = captured.get("payload", {})
    assert payload.get("order_number") == "YLA2026060300002"
    assert payload.get("transaction_id", "").startswith("MOCK_")
    assert payload.get("success") is True


@pytest.mark.asyncio
async def test_create_order_swallows_trigger_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """trigger 失败/超时不应炸主流程：fire-and-forget 静默吞下。"""
    monkeypatch.setenv("MOCK_PAY_BASE_URL", "http://mock-pay-stub:8001")
    provider = MockPaymentProvider()

    class _RaisingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "_RaisingClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError("simulated mock-pay-stub down")

    with patch("app.services.providers.payment.mock.httpx.AsyncClient", _RaisingClient):
        # 主路径必须仍然成功返回
        result = await provider.create_order(
            OrderDTO(order_number="YLA2026060300003", amount_yuan=149)
        )
        await asyncio.sleep(0.05)  # 让 background task 跑完它的 except

    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_create_order_empty_mock_pay_base_url_is_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """空字符串/纯空白 MOCK_PAY_BASE_URL 视同未设置。"""
    monkeypatch.setenv("MOCK_PAY_BASE_URL", "   ")
    provider = MockPaymentProvider()

    with patch("httpx.AsyncClient") as mock_client:
        await provider.create_order(
            OrderDTO(order_number="YLA2026060300004", amount_yuan=299)
        )

    mock_client.assert_not_called()
