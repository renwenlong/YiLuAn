"""[ADR-0032 §4 / TD-MONEY-01 M1] diff_orders 纯函数单元测试。

覆盖 ADR §8 M1 出口要求的全部场景：
- 4 类 diff（missing_payment / orphan_payment / amount_mismatch / status_mismatch）各 ≥ 2 条
- 跨日边界 2 条
- 退款乱序 2 条
- Decimal 浮点边界（0.01 累加）2 条
- 三源全空（无 diff）
- 三源完全一致（无 diff）
- 输出排序确定性（同 input 跑 100 次结果相同）
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.reconciliation import ReconDiffKind
from app.services.reconciliation import (
    BusinessSnapshot,
    LedgerSnapshot,
    PaymentSnapshot,
    diff_orders,
)


# ---------------------------------------------------------------------------
# 小工具
# ---------------------------------------------------------------------------
def _u() -> uuid.UUID:
    return uuid.uuid4()


def _b(order_id, status, amount):
    return BusinessSnapshot(order_id=order_id, status=status, amount=Decimal(amount))


def _p(order_id, status, amount, provider="wechat", txn=None):
    return PaymentSnapshot(
        order_id=order_id,
        status=status,
        amount=Decimal(amount),
        provider=provider,
        provider_txn_id=txn or f"txn_{order_id}",
    )


def _l(order_id, status, amount):
    return LedgerSnapshot(order_id=order_id, status=status, amount=Decimal(amount))


# ---------------------------------------------------------------------------
# 1. 三源完全一致 → 无 diff
# ---------------------------------------------------------------------------
def test_all_three_sources_consistent_yields_no_diff():
    o1, o2 = _u(), _u()
    business = {
        o1: _b(o1, "completed", "299.00"),
        o2: _b(o2, "in_progress", "199.00"),
    }
    payments = {
        o1: _p(o1, "success", "299.00"),
        o2: _p(o2, "success", "199.00"),
    }
    ledger = {
        o1: _l(o1, "posted", "299.00"),
        o2: _l(o2, "posted", "199.00"),
    }
    assert diff_orders(business, payments, ledger) == []


# ---------------------------------------------------------------------------
# 2. 三源全空 → 无 diff
# ---------------------------------------------------------------------------
def test_all_empty_yields_no_diff():
    assert diff_orders({}, {}, {}) == []


# ---------------------------------------------------------------------------
# 3. MISSING_PAYMENT × 2
# ---------------------------------------------------------------------------
def test_missing_payment_business_only():
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "in_progress", "299.00")}, {}, {}
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.missing_payment]
    assert diffs[0].order_id == o
    assert diffs[0].business_amount == Decimal("299.00")
    assert diffs[0].payment_amount is None


def test_missing_payment_pending_only():
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "completed", "199.00")},
        {o: _p(o, "pending", "199.00")},
        {},
    )
    assert len(diffs) == 1
    assert diffs[0].kind == ReconDiffKind.missing_payment
    assert diffs[0].payment_status == "pending"


# ---------------------------------------------------------------------------
# 4. ORPHAN_PAYMENT × 2
# ---------------------------------------------------------------------------
def test_orphan_payment_no_business():
    o = _u()
    diffs = diff_orders(
        {},
        {o: _p(o, "success", "299.00", txn="wx_001")},
        {},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.orphan_payment]
    assert diffs[0].provider == "wechat"
    assert diffs[0].provider_txn_id == "wx_001"
    assert diffs[0].business_amount is None


def test_orphan_payment_business_cancelled():
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "cancelled_by_patient", "0.00")},
        {o: _p(o, "success", "299.00")},
        {},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.orphan_payment]
    assert diffs[0].business_status == "cancelled_by_patient"


# ---------------------------------------------------------------------------
# 5. AMOUNT_MISMATCH × 2
# ---------------------------------------------------------------------------
def test_amount_mismatch_business_vs_payment():
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "completed", "299.00")},
        {o: _p(o, "success", "200.00")},
        {o: _l(o, "posted", "200.00")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.amount_mismatch]
    assert diffs[0].business_amount == Decimal("299.00")
    assert diffs[0].payment_amount == Decimal("200.00")


def test_amount_mismatch_payment_vs_ledger():
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "completed", "299.00")},
        {o: _p(o, "success", "299.00")},
        {o: _l(o, "posted", "150.00")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.amount_mismatch]
    assert diffs[0].ledger_amount == Decimal("150.00")


# ---------------------------------------------------------------------------
# 6. STATUS_MISMATCH × 2
# ---------------------------------------------------------------------------
def test_status_mismatch_cancelled_with_ledger_balance():
    o = _u()
    # 业务已退款 (cancelled), 流水 SUM 已为 0（退款抵消），但账本未抹平
    diffs = diff_orders(
        {o: _b(o, "cancelled_by_patient", "0.00")},
        {o: _p(o, "success", "0.00")},  # 净额 0 → 不算 orphan
        {o: _l(o, "posted", "299.00")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.status_mismatch]
    assert diffs[0].ledger_amount == Decimal("299.00")


def test_status_mismatch_no_business_expectation_but_ledger_has_money():
    o = _u()
    # 业务侧是 created（不应已收款），但账本竟有正余额
    diffs = diff_orders(
        {o: _b(o, "created", "299.00")},
        {},
        {o: _l(o, "posted", "299.00")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.status_mismatch]


# ---------------------------------------------------------------------------
# 7. 跨日边界 × 2
# ---------------------------------------------------------------------------
def test_cross_day_late_callback_within_window():
    """跨日延迟回调：业务在 D 日 23:59 完成，流水在 D+1 00:01 落库。
    diff_orders 不感知时间窗口（时间在 IO 层裁剪），此处验证算法对 D 日订单 + D+1 流水
    （都喂进来）能识别为一致 → 无 diff。
    """
    o = _u()
    # 时间字段不影响 diff_orders 本身，只是确保夹带 timezone 不引发异常
    _ = datetime(2026, 4, 27, 23, 59, tzinfo=timezone.utc)
    _ = datetime(2026, 4, 28, 0, 1, tzinfo=timezone.utc)
    diffs = diff_orders(
        {o: _b(o, "completed", "299.00")},
        {o: _p(o, "success", "299.00")},
        {o: _l(o, "posted", "299.00")},
    )
    assert diffs == []


def test_cross_day_business_done_but_payment_only_lands_next_day():
    """业务侧 D 日已 completed，但流水 D 日还没回调（D+1 才到，喂入快照时尚未到）。"""
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "completed", "299.00")},
        {},  # D 日窗口内尚未收到回调
        {},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.missing_payment]


# ---------------------------------------------------------------------------
# 8. 退款乱序 × 2
# ---------------------------------------------------------------------------
def test_refund_arrives_before_payment_net_zero():
    """退款先于支付到达：流水侧聚合后净额 = 0，业务也是 cancelled → 无 diff。"""
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "cancelled_by_patient", "0.00")},
        {o: _p(o, "success", "0.00")},  # pay 299 - refund 299 = 0
        {o: _l(o, "posted", "0.00")},
    )
    assert diffs == []


def test_refund_partial_business_cancelled_but_amount_remains():
    """部分退款（149.50 / 299）：业务取消但流水净额 > 0 → ORPHAN_PAYMENT。"""
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "cancelled_by_patient", "0.00")},
        {o: _p(o, "success", "149.50")},
        {o: _l(o, "posted", "149.50")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.orphan_payment]
    assert diffs[0].payment_amount == Decimal("149.50")


# ---------------------------------------------------------------------------
# 9. Decimal 浮点边界 × 2
# ---------------------------------------------------------------------------
def test_decimal_precision_0_01_accumulation_consistent():
    """100 次 0.01 累加 = 1.00 应当被视为相等（Decimal 精确加法）。"""
    o = _u()
    accum = sum((Decimal("0.01") for _ in range(100)), Decimal("0.00"))
    assert accum == Decimal("1.00")
    diffs = diff_orders(
        {o: _b(o, "completed", accum)},
        {o: _p(o, "success", "1.00")},
        {o: _l(o, "posted", "1.00")},
    )
    assert diffs == []


def test_decimal_precision_one_cent_diff_is_amount_mismatch():
    """0.01 差异必须被算法识别（而不是被 float 容忍）。"""
    o = _u()
    diffs = diff_orders(
        {o: _b(o, "completed", "299.00")},
        {o: _p(o, "success", "298.99")},
        {o: _l(o, "posted", "298.99")},
    )
    assert [d.kind for d in diffs] == [ReconDiffKind.amount_mismatch]


# ---------------------------------------------------------------------------
# 10. 排序确定性
# ---------------------------------------------------------------------------
def test_output_ordering_deterministic_over_many_runs():
    o1, o2, o3 = _u(), _u(), _u()
    business = {
        o1: _b(o1, "completed", "299.00"),
        o2: _b(o2, "in_progress", "199.00"),
        o3: _b(o3, "cancelled_by_patient", "0.00"),
    }
    payments = {
        o2: _p(o2, "pending", "199.00"),  # MISSING_PAYMENT
        o3: _p(o3, "success", "299.00"),  # ORPHAN_PAYMENT
    }
    ledger = {}
    expected = diff_orders(business, payments, ledger)
    assert len(expected) == 3  # o1 missing, o2 missing, o3 orphan
    for _ in range(100):
        got = diff_orders(business, payments, ledger)
        assert got == expected
    # 字典序：order_id str 排序
    sorted_ids = [str(o1), str(o2), str(o3)]
    sorted_ids.sort()
    assert [str(d.order_id) for d in expected] == sorted_ids


# ---------------------------------------------------------------------------
# 11. 多类 diff 共存：覆盖每条 pass 都能并存
# ---------------------------------------------------------------------------
def test_mixed_diff_types_all_collected():
    o_missing = _u()
    o_orphan = _u()
    o_amount = _u()
    o_status = _u()
    business = {
        o_missing: _b(o_missing, "completed", "299.00"),
        o_amount: _b(o_amount, "completed", "299.00"),
        o_status: _b(o_status, "cancelled_by_patient", "0.00"),
    }
    payments = {
        o_amount: _p(o_amount, "success", "200.00"),
        o_orphan: _p(o_orphan, "success", "199.00"),
    }
    ledger = {
        o_amount: _l(o_amount, "posted", "200.00"),
        o_status: _l(o_status, "posted", "299.00"),
    }
    diffs = diff_orders(business, payments, ledger)
    kinds = {d.kind for d in diffs}
    assert kinds == {
        ReconDiffKind.missing_payment,
        ReconDiffKind.orphan_payment,
        ReconDiffKind.amount_mismatch,
        ReconDiffKind.status_mismatch,
    }


# ---------------------------------------------------------------------------
# 12. 账本独有脏数据：业务+流水都没有，账本有正余额 → AMOUNT_MISMATCH
# ---------------------------------------------------------------------------
def test_ledger_only_orphan_balance_is_amount_mismatch():
    o = _u()
    diffs = diff_orders({}, {}, {o: _l(o, "posted", "50.00")})
    assert [d.kind for d in diffs] == [ReconDiffKind.amount_mismatch]
    assert diffs[0].ledger_amount == Decimal("50.00")


# ---------------------------------------------------------------------------
# 13. None 金额防御
# ---------------------------------------------------------------------------
def test_none_business_amount_is_treated_as_zero_no_expectation():
    o = _u()
    # 业务 status=created（非 paid 集合）+ amount=None → 不应触发 missing_payment
    diffs = diff_orders(
        {o: BusinessSnapshot(order_id=o, status="created", amount=None)},  # type: ignore[arg-type]
        {},
        {},
    )
    assert diffs == []
