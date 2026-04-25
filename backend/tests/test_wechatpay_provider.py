"""WechatPaymentProvider real-credential smoke test.

This file historically held an ``xfail`` marker tied to Blocker B-01
(微信支付商户号 / APIv3 凭据未到位). Per A-2604-03 the test is converted
to an env-var gated skip so CI reports remain clean (no xfail noise) and
the test will actually execute the moment ``WECHATPAY_REAL_CREDS=1`` is
exported on a runner that has the real credentials configured.

To enable locally::

    export WECHATPAY_REAL_CREDS=1
    export WECHAT_MCH_ID=...
    export WECHAT_API_V3_KEY=...
    export WECHAT_MERCHANT_SERIAL_NO=...
    export WECHAT_MERCHANT_PRIVATE_KEY_PATH=...
    pytest backend/tests/test_wechatpay_provider.py -q
"""

from __future__ import annotations

import os

import pytest


@pytest.mark.skipif(
    not os.getenv("WECHATPAY_REAL_CREDS"),
    reason="B-01 blocked: real WeChat Pay merchant credentials not provisioned",
)
@pytest.mark.asyncio
async def test_wechatpay_provider_with_real_credentials():
    """End-to-end smoke against the real WeChat Pay sandbox/prod APIv3.

    Verifies that ``WechatPaymentProvider.create_order`` can hand back a
    ``prepay_id``-bearing payload when wired to the real merchant
    credentials. Skipped by default until B-01 is unblocked.
    """
    from app.services.providers.payment.wechat import WechatPaymentProvider
    from app.schemas.order import OrderDTO

    provider = WechatPaymentProvider()
    order = OrderDTO(
        out_trade_no=f"e2e-{os.getpid()}",
        total_fee=1,  # 1 cent sandbox amount
        body="YiLuAn e2e smoke",
        openid=os.environ["WECHAT_TEST_OPENID"],
    )
    result = await provider.create_order(order)
    assert "prepay_id" in result, result
