"""Real-credential e2e tests for WeChat Pay (Blocker B-01).

All tests in this module are gated by ``WECHATPAY_REAL_CREDS=1``. They
will be enabled the moment the merchant ID, APIv3 key, merchant private
key and platform certificates are provisioned (see B-01).

Test surface (3 functions):
  - ``test_create_unified_order``   -- POST /v3/pay/transactions/jsapi
  - ``test_callback_signature_verify`` -- WechatPaymentProvider.verify_callback
  - ``test_refund_flow``             -- POST /v3/refund/domestic/refunds

These are skeletons authored under A-2604-05; concrete assertions are
TODO and must be filled in once a sandbox merchant account is available.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("WECHATPAY_REAL_CREDS"),
    reason="B-01 blocked: real WeChat Pay merchant credentials not provisioned",
)


@pytest.mark.asyncio
async def test_create_unified_order():
    """统一下单：调用 WechatPaymentProvider.create_order 并断言返回 prepay_id。

    TODO(A-2604-05 / B-01):
      1. 注入沙箱 merchant_id / apiv3_key / 私钥路径的 Settings override；
      2. 构造 OrderDTO（金额 1 分）调用 ``provider.create_order``；
      3. 断言返回值含 ``prepay_id`` 且形如 ``wx<32hex>``；
      4. 校验微信端 HTTP 200，记录 trace_id 用于人工对账。
    """
    pytest.fail("TODO(B-01): implement once sandbox merchant credentials land")


@pytest.mark.asyncio
async def test_callback_signature_verify():
    """回调验签：将真实 v3 回调样例喂给 verify_callback 验证签名 + 解密。

    TODO(A-2604-05 / B-01):
      1. 抓取一份沙箱真实回调（headers + body）入 fixture；
      2. 调用 ``WechatPaymentProvider.verify_callback(headers, body)``；
      3. 断言解密后的 resource 含 ``out_trade_no`` / ``trade_state == 'SUCCESS'``；
      4. 验证 5 分钟时间戳窗口防重放（D-011）。
    """
    pytest.fail("TODO(B-01): implement after capturing sandbox callback fixture")


@pytest.mark.asyncio
async def test_refund_flow():
    """退款链路：下单成功后发起退款，验证状态机推进 + 退款回调验签。

    TODO(A-2604-05 / B-01):
      1. 复用 create_order 流程拿到 out_trade_no；
      2. 调用 ``provider.refund(RefundDTO(...))`` 触发退款单；
      3. 等待退款回调（或主动 query）；
      4. 断言 PaymentService 状态机推进至 ``refunded``，且 refund_log 记录幂等。
    """
    pytest.fail("TODO(B-01): implement once refund sandbox flow is reachable")
