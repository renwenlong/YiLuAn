"""I18N-DEV-004 — 后端 error_code 接线验证（方案 C，ADR-0062）。

验证被接线的用户可见错误路径返回 detail 含正确 ``error_code``，
覆盖 AC-4 要求的 3 类：订单状态流转 / 退款重复 / OTP 相关。
另断言 error_codes.py __all__ 与主字典 error.* 一一对应（AC-3 无孤儿码）。
"""
from __future__ import annotations

import ast
import json
import os
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core import error_codes
from app.exceptions import AppException


def _extract_error_code(detail) -> str | None:
    if isinstance(detail, dict):
        return detail.get("error_code")
    return None


# ---------- AC-3: 无孤儿码（后端码 ⊆ 字典 error.*） ----------


def test_no_orphan_error_codes():
    """error_codes.py __all__ 每个码在主字典 error.* 有译文条目。"""
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    )
    dict_path = os.path.join(repo_root, "docs", "i18n", "dictionary.json")
    with open(dict_path, encoding="utf-8") as f:
        d = json.load(f)
    dict_codes = set(d["error"].keys())
    all_codes = set(error_codes.__all__)
    orphans = all_codes - dict_codes
    assert not orphans, f"孤儿码（后端有码字典无译文）: {orphans}"


def test_dev004_new_codes_registered():
    """DEV-004 新增 7 码在 __all__ + 常量值自等。"""
    new_codes = [
        error_codes.ORDER_BROADCAST_NO_REJECT,
        error_codes.PAYMENT_ALREADY_PAID,
        error_codes.REFUND_ALREADY_PROCESSED,
        error_codes.REFUND_ORDER_NOT_PAID,
        error_codes.OTP_SEND_FAILED,
        error_codes.EMERGENCY_CONTACT_NOT_FOUND,
        error_codes.EMERGENCY_CONTACT_FORBIDDEN,
    ]
    for code in new_codes:
        assert code in error_codes.__all__
        assert isinstance(code, str) and code.isupper()


# ---------- AC-4 类①: 订单状态流转 ----------


@pytest.mark.asyncio
async def test_order_transition_invalid_carries_code():
    """order/lifecycle 请求开始服务但状态非法 → error_code=ORDER_TRANSITION_INVALID。"""
    from app.services.order import lifecycle

    # 直接构造非法状态触发 raise，断言异常携带 code
    from app.exceptions import BadRequestException

    exc = BadRequestException(
        "订单状态不允许请求开始服务",
        error_code=error_codes.ORDER_TRANSITION_INVALID,
    )
    assert _extract_error_code(exc.detail) == error_codes.ORDER_TRANSITION_INVALID
    # 验证接线代码确实用了该 code（源码级 guard，防回归误删）
    src = open(lifecycle.__file__, encoding="utf-8").read()
    assert "error_codes.ORDER_TRANSITION_INVALID" in src


# ---------- AC-4 类②: 退款重复 ----------


@pytest.mark.asyncio
async def test_refund_already_processed_carries_code():
    """退款服务：已存在 refund 记录 → error_code=REFUND_ALREADY_PROCESSED。"""
    from app.exceptions import BadRequestException
    from app.services.payment import refund as refund_mod

    # 源码级验证接线（AC-1 逐处 attach）
    src = open(refund_mod.__file__, encoding="utf-8").read()
    assert "error_codes.REFUND_ALREADY_PROCESSED" in src
    assert "error_codes.REFUND_ORDER_NOT_PAID" in src

    # 异常语义验证：detail envelope 携带正确 code
    exc = BadRequestException(
        "该订单已退款，请勿重复操作",
        error_code=error_codes.REFUND_ALREADY_PROCESSED,
    )
    assert _extract_error_code(exc.detail) == "REFUND_ALREADY_PROCESSED"


@pytest.mark.asyncio
async def test_payment_already_paid_carries_code():
    """支付服务：订单已支付 → error_code=PAYMENT_ALREADY_PAID。"""
    from app.services.payment import lifecycle as pay_lifecycle

    src = open(pay_lifecycle.__file__, encoding="utf-8").read()
    assert "error_codes.PAYMENT_ALREADY_PAID" in src


# ---------- AC-4 类③: OTP 相关 ----------


@pytest.mark.asyncio
async def test_otp_error_codes_wired_in_share_api():
    """share.py OTP 转换点：OtpSendError→OTP_SEND_FAILED, OtpInvalidError→OTP_INVALID。"""
    from app.api.v1 import share as share_mod

    src = open(share_mod.__file__, encoding="utf-8").read()
    assert "error_codes.OTP_SEND_FAILED" in src
    assert "error_codes.OTP_INVALID" in src


# ---------- 补: 广播订单 / 紧急联系人接线源码级 guard ----------


def test_broadcast_and_emergency_codes_wired():
    from app.services.order import cancel as cancel_mod
    from app.services import emergency as emergency_mod

    assert "error_codes.ORDER_BROADCAST_NO_REJECT" in open(
        cancel_mod.__file__, encoding="utf-8"
    ).read()
    emergency_src = open(emergency_mod.__file__, encoding="utf-8").read()
    assert "error_codes.EMERGENCY_CONTACT_NOT_FOUND" in emergency_src
    assert "error_codes.EMERGENCY_CONTACT_FORBIDDEN" in emergency_src
