"""[BACKLOG-OUTBOUND-PROVIDERS] WeChat Pay 4xx/5xx/network 三档分类测试.

验证 create_order / refund 接 @outbound_call 后, httpx 失败被
classify_httpx_exception 正确分档:
  - 4xx (签名/参数错) → NonRetryableError, 不污染 CB
  - 5xx → RetryableError (out_trade_no/out_refund_no 幂等, 重试安全)
  - network (ConnectError/Timeout) → RetryableError
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.providers.payment.base import OrderDTO, RefundDTO
from app.services.providers.payment.wechat import WechatPaymentProvider
from app.utils.outbound import (
    NonRetryableError,
    RetryableError,
    reset_circuit_breakers,
)


def _provider(monkeypatch) -> WechatPaymentProvider:
    monkeypatch.setattr("app.config.settings.wechat_pay_mch_id", "16000000")
    monkeypatch.setattr("app.config.settings.wechat_app_id", "wxtest")
    p = WechatPaymentProvider()
    # Force the real-call branch + bypass real signing.
    p._has_credentials = True
    p.mch_id = "16000000"
    p.app_id = "wxtest"
    p.notify_url = "https://m.yiluan.cn/pay/notify"
    return p


def _mock_resp(status_code: int, json_data: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data or {},
        request=httpx.Request("POST", "https://api.mch.weixin.qq.com/"),
    )


def _patch_client(mock_resp=None, side_effect=None):
    client = AsyncMock()
    if side_effect is not None:
        client.post.side_effect = side_effect
    else:
        client.post.return_value = mock_resp
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return patch(
        "app.services.providers.payment.wechat.httpx.AsyncClient",
        return_value=client,
    )


def _order() -> OrderDTO:
    return OrderDTO(
        order_number="YLA-TEST-0001",
        amount_yuan=Decimal("299.00"),
        description="测试",
        openid="o_test",
    )


def _refund() -> RefundDTO:
    return RefundDTO(
        refund_id="RF-0001",
        trade_no="YLA-TEST-0001",
        total_yuan=Decimal("299.00"),
        refund_yuan=Decimal("299.00"),
    )


@pytest.fixture(autouse=True)
def _reset_cb():
    reset_circuit_breakers()
    yield
    reset_circuit_breakers()


@pytest.fixture(autouse=True)
def _stub_sign(monkeypatch):
    monkeypatch.setattr(
        WechatPaymentProvider, "_build_auth_header", lambda self, *a, **k: {}
    )
    monkeypatch.setattr(
        WechatPaymentProvider, "_rsa_sign", lambda self, *a, **k: "sig"
    )


# --- create_order -----------------------------------------------------------


@pytest.mark.asyncio
async def test_create_order_4xx_non_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(400, {"code": "PARAM_ERROR"})):
        with pytest.raises(NonRetryableError):
            await p.create_order(_order())


@pytest.mark.asyncio
async def test_create_order_5xx_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(500, {"code": "SYSTEM_ERROR"})):
        with pytest.raises(RetryableError):
            await p.create_order(_order())


@pytest.mark.asyncio
async def test_create_order_network_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(side_effect=httpx.ConnectError("conn refused")):
        with pytest.raises(RetryableError):
            await p.create_order(_order())


@pytest.mark.asyncio
async def test_create_order_success(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(200, {"prepay_id": "wx_pp_123"})):
        out = await p.create_order(_order())
    assert out["prepay_id"] == "wx_pp_123"
    assert out["status"] == "pending"


# --- refund -----------------------------------------------------------------


@pytest.mark.asyncio
async def test_refund_4xx_non_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(403, {"code": "SIGN_ERROR"})):
        with pytest.raises(NonRetryableError):
            await p.refund(_refund())


@pytest.mark.asyncio
async def test_refund_5xx_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(502, {"code": "BAD_GATEWAY"})):
        with pytest.raises(RetryableError):
            await p.refund(_refund())


@pytest.mark.asyncio
async def test_refund_network_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(RetryableError):
            await p.refund(_refund())


@pytest.mark.asyncio
async def test_refund_success(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(_mock_resp(200, {"out_refund_no": "RF-0001", "status": "SUCCESS"})):
        out = await p.refund(_refund())
    assert out["refund_id"] == "RF-0001"
    assert out["status"] == "success"
