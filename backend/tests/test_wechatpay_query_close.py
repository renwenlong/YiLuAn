"""S3-PAY-WECHAT-V3-QUERY-CLOSE-WIRE — query() / close_order() 接线测试.

覆盖 wechat.py 新接通的两条生产路径:
  - query():  GET /v3/pay/transactions/out-trade-no/{no}?mchid={mch}
              → 解析 trade_state 映射内部状态 (AC-1)
  - close_order(): POST .../{no}/close, body {mchid}, 成功 204/200 (AC-2)
  - @outbound_call 4xx/5xx/network 分类 (AC-3)
  - 无凭据 mock 回退不破 (AC-4)

复用 test_wechatpay_outbound_classify.py 的 httpx.AsyncClient monkeypatch 手法.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.providers.payment.base import OrderDTO
from app.services.providers.payment.wechat import (
    WechatPaymentProvider,
    _map_trade_state,
)
from app.utils.outbound import (
    NonRetryableError,
    RetryableError,
    reset_circuit_breakers,
)


def _provider(monkeypatch, *, has_creds: bool = True) -> WechatPaymentProvider:
    monkeypatch.setattr("app.config.settings.wechat_pay_mch_id", "16000000")
    monkeypatch.setattr("app.config.settings.wechat_app_id", "wxtest")
    p = WechatPaymentProvider()
    p._has_credentials = has_creds
    p.mch_id = "16000000"
    p.app_id = "wxtest"
    p.notify_url = "https://m.yiluan.cn/pay/notify"
    return p


def _mock_resp(status_code: int, json_data: dict | None = None) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json=json_data if json_data is not None else {},
        request=httpx.Request("GET", "https://api.mch.weixin.qq.com/"),
    )


def _patch_client(*, get_resp=None, post_resp=None, side_effect=None):
    """Patch httpx.AsyncClient; wire .get / .post return or side_effect."""
    client = AsyncMock()
    if side_effect is not None:
        client.get.side_effect = side_effect
        client.post.side_effect = side_effect
    else:
        client.get.return_value = get_resp
        client.post.return_value = post_resp
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


# --- _map_trade_state (AC-1 mapping) ----------------------------------------


@pytest.mark.parametrize(
    "trade_state,expected",
    [
        ("SUCCESS", "success"),
        ("REFUND", "refund"),
        ("NOTPAY", "pending"),
        ("USERPAYING", "pending"),
        ("CLOSED", "closed"),
        ("REVOKED", "closed"),
        ("PAYERROR", "failed"),
        ("success", "success"),  # case-insensitive
        ("WEIRD_UNKNOWN", "unknown"),
        ("", "unknown"),
    ],
)
def test_map_trade_state(trade_state, expected):
    assert _map_trade_state(trade_state) == expected


# --- query() ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_success_maps_trade_state(monkeypatch):
    p = _provider(monkeypatch)
    resp = _mock_resp(
        200,
        {
            "out_trade_no": "YLA-TEST-0001",
            "transaction_id": "4200001234",
            "trade_state": "SUCCESS",
            "trade_state_desc": "支付成功",
        },
    )
    with _patch_client(get_resp=resp):
        out = await p.query(_order())
    assert out["trade_state"] == "SUCCESS"
    assert out["status"] == "success"
    assert out["transaction_id"] == "4200001234"
    assert out["out_trade_no"] == "YLA-TEST-0001"


@pytest.mark.asyncio
async def test_query_notpay_maps_pending(monkeypatch):
    p = _provider(monkeypatch)
    resp = _mock_resp(200, {"out_trade_no": "YLA-TEST-0001", "trade_state": "NOTPAY"})
    with _patch_client(get_resp=resp):
        out = await p.query(_order())
    assert out["status"] == "pending"


@pytest.mark.asyncio
async def test_query_no_credentials_mock(monkeypatch):
    """AC-4: 无凭据保持 mock 行为 (trade_state=SUCCESS)."""
    p = _provider(monkeypatch, has_creds=False)
    out = await p.query(_order())
    assert out["trade_state"] == "SUCCESS"
    assert out["out_trade_no"] == "YLA-TEST-0001"


@pytest.mark.asyncio
async def test_query_4xx_non_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(get_resp=_mock_resp(400, {"code": "PARAM_ERROR"})):
        with pytest.raises(NonRetryableError):
            await p.query(_order())


@pytest.mark.asyncio
async def test_query_5xx_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(get_resp=_mock_resp(500, {"code": "SYSTEM_ERROR"})):
        with pytest.raises(RetryableError):
            await p.query(_order())


@pytest.mark.asyncio
async def test_query_network_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(side_effect=httpx.ConnectError("conn refused")):
        with pytest.raises(RetryableError):
            await p.query(_order())


# --- close_order() ----------------------------------------------------------


@pytest.mark.asyncio
async def test_close_order_success_204(monkeypatch):
    """AC-2: WeChat close 返回 204 No Content 视为成功."""
    p = _provider(monkeypatch)
    with _patch_client(post_resp=_mock_resp(204)):
        out = await p.close_order("YLA-TEST-0001")
    assert out["status"] == "success"


@pytest.mark.asyncio
async def test_close_order_success_200(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(post_resp=_mock_resp(200)):
        out = await p.close_order("YLA-TEST-0001")
    assert out["status"] == "success"


@pytest.mark.asyncio
async def test_close_order_no_credentials_mock(monkeypatch):
    """AC-4: 无凭据保持 mock 成功."""
    p = _provider(monkeypatch, has_creds=False)
    out = await p.close_order("YLA-TEST-0001")
    assert out["status"] == "success"


@pytest.mark.asyncio
async def test_close_order_4xx_non_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(post_resp=_mock_resp(400, {"code": "ORDER_CLOSED"})):
        with pytest.raises(NonRetryableError):
            await p.close_order("YLA-TEST-0001")


@pytest.mark.asyncio
async def test_close_order_5xx_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(post_resp=_mock_resp(502, {"code": "BAD_GATEWAY"})):
        with pytest.raises(RetryableError):
            await p.close_order("YLA-TEST-0001")


@pytest.mark.asyncio
async def test_close_order_network_retryable(monkeypatch):
    p = _provider(monkeypatch)
    with _patch_client(side_effect=httpx.ReadTimeout("timeout")):
        with pytest.raises(RetryableError):
            await p.close_order("YLA-TEST-0001")
