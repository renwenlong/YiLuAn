"""Real-credential e2e tests for Aliyun SMS (Blocker B-02).

All tests in this module are gated by ``ALIYUN_SMS_REAL_CREDS=1``. They
will be enabled once the AccessKey, signature 签名 and template 备案号
are provisioned (see B-02).

Test surface (2 functions):
  - ``test_send_otp_real``      -- 发送一次性验证码到白名单手机号
  - ``test_send_template_real`` -- 发送通知类模板短信

These are skeletons authored under A-2604-05; concrete assertions are
TODO and must be filled in once an SMS test signature is registered.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("ALIYUN_SMS_REAL_CREDS"),
    reason="B-02 blocked: real Aliyun SMS credentials / signature not provisioned",
)


@pytest.mark.asyncio
async def test_send_otp_real():
    """OTP 真发：向白名单手机号发送验证码并校验 sms_send_log 落库。

    TODO(A-2604-05 / B-02):
      1. 注入真实 AccessKey + 签名 + OTP 模板号 Settings override；
      2. 调用 ``SMSProvider.send_otp(phone=os.environ['SMS_TEST_PHONE'], code='123456')``；
      3. 断言返回 ``request_id`` 非空且 ``status == 'success'``；
      4. 查询 ``sms_send_log`` 表确认 phone_hash + masked + status 落库（D-033）。
    """
    pytest.fail("TODO(B-02): implement after Aliyun signature is approved")


@pytest.mark.asyncio
async def test_send_template_real():
    """模板短信真发：发送一条订单通知类模板短信，校验回执。

    TODO(A-2604-05 / B-02):
      1. 注入通知类模板号；
      2. 调用 ``SMSProvider.send_template(phone=..., template_code=..., params={...})``；
      3. 断言 Aliyun 返回 ``Code == 'OK'``；
      4. 校验 sms_send_log 中 ``template_code`` 写入正确（不写 params，遵循 D-033 决策 1）。
    """
    pytest.fail("TODO(B-02): implement after notification template is approved")
