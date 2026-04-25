"""ADR-0030: Decimal money migration — boundary & invariant tests.

These tests pin the Decimal contract independently of the existing test suite,
so a future regression to float-based math fails fast here.
"""

from decimal import Decimal, ROUND_HALF_UP

import pytest

from app.services.order import SERVICE_PRICES
from app.services.providers.payment.base import (
    OrderDTO,
    RefundDTO,
    _to_decimal,
)


class TestServicePrices:
    def test_service_prices_are_decimal(self):
        for service_type, price in SERVICE_PRICES.items():
            assert isinstance(price, Decimal), (
                f"SERVICE_PRICES[{service_type}] must be Decimal, got {type(price)}"
            )

    def test_service_prices_two_decimal_places(self):
        for service_type, price in SERVICE_PRICES.items():
            quantized = price.quantize(Decimal("0.01"))
            assert price == quantized, f"{service_type}={price} not in fen precision"

    def test_service_prices_match_business_constants(self):
        # 业务约定，三端共享：full=299 / half=199 / errand=149
        assert SERVICE_PRICES["full_accompany"] == Decimal("299.00")
        assert SERVICE_PRICES["half_accompany"] == Decimal("199.00")
        assert SERVICE_PRICES["errand"] == Decimal("149.00")


class TestDecimalArithmetic:
    def test_classic_float_pitfall_avoided(self):
        # Float: 0.1 + 0.2 == 0.30000000000000004
        # Decimal: 必须精确
        assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")

    def test_partial_refund_no_drift(self):
        # 订单 299.00，退款 199.99，余 99.01，不允许漂移
        total = Decimal("299.00")
        refund = Decimal("199.99")
        remainder = total - refund
        assert remainder == Decimal("99.01")

    def test_ratio_refund_quantize(self):
        # 0.7 比例退款 299.00 → 209.30
        total = Decimal("299.00")
        ratio = Decimal("0.7")
        refund = (total * ratio).quantize(Decimal("0.01"))
        assert refund == Decimal("209.30")

    def test_half_up_rounding(self):
        # 银行家舍入 vs HALF_UP：业务用 HALF_UP
        assert Decimal("0.125").quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) == Decimal("0.13")
        assert Decimal("0.135").quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        ) == Decimal("0.14")


class TestProviderDTOCoercion:
    def test_to_decimal_from_float_via_str(self):
        # float 走 str 中转，避免 IEEE 754 噪音泄漏
        result = _to_decimal(0.1)
        assert result == Decimal("0.1")

    def test_to_decimal_passthrough(self):
        d = Decimal("299.00")
        assert _to_decimal(d) is d

    def test_to_decimal_from_int(self):
        assert _to_decimal(299) == Decimal("299")

    def test_order_dto_yuan_to_fen_exact(self):
        # 关键：传给微信支付的分必须精确，不能因 float 漂移多/少 1 分
        dto = OrderDTO(order_number="X", amount_yuan=Decimal("299.00"))
        fen = int((dto.amount_yuan * 100).to_integral_value(rounding=ROUND_HALF_UP))
        assert fen == 29900

    def test_refund_dto_decimal_arithmetic(self):
        dto = RefundDTO(
            trade_no="WX_T",
            refund_id="R_1",
            total_yuan=Decimal("299.00"),
            refund_yuan=Decimal("199.99"),
        )
        # 类型不变形
        assert isinstance(dto.total_yuan, Decimal)
        assert isinstance(dto.refund_yuan, Decimal)
        # 余额计算精确
        assert dto.total_yuan - dto.refund_yuan == Decimal("99.01")


class TestSchemaSerialization:
    """API 出参契约：金额仍是 number (float)，不是字符串 — 前端零改动。"""

    def test_order_response_serializes_price_as_number(self):
        from app.schemas.order import OrderResponse
        from datetime import datetime
        from uuid import uuid4

        resp = OrderResponse(
            id=uuid4(),
            order_number="ORD_T",
            user_id=uuid4(),
            patient_id=uuid4(),
            companion_id=None,
            service_type="full_accompany",
            hospital_id=uuid4(),
            appointment_date="2026-05-01",
            appointment_time="09:00",
            description="t",
            price=Decimal("299.00"),
            status="created",
            timeline_index=0,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        dumped = resp.model_dump(mode="json")
        assert isinstance(dumped["price"], float), (
            "API 出参 price 必须是 number，前端契约不能破"
        )
        assert dumped["price"] == 299.00
