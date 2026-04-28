"""[ADR-0032 §4] 三方对账纯函数算法。

输入：三源快照 ``Mapping[UUID, *Snapshot]``（纯数据，无 IO）。
输出：``list[ReconDiff]``，按 ``(str(order_id) or "", kind.value)`` 字典序排序，
对相同输入永远得到相同结果，便于在测试中用 ``==`` 直接断言。

四类 diff（ADR §2.3）：

- ``MISSING_PAYMENT``: 业务侧应收 > 0 但流水侧无 success 流水
- ``ORPHAN_PAYMENT``:  流水侧有 success 但业务侧不存在/已 cancelled
- ``AMOUNT_MISMATCH``: 业务/流水/账本三者金额不齐
- ``STATUS_MISMATCH``: 金额相等但状态相位错位

业务/账本「应不应该有钱」的判定与具体业务状态值耦合最低，因此本模块
不直接 import ``OrderStatus``/``WalletLedgerReason`` 等枚举，而是采用
字符串/集合的方式（IO 层负责把 enum.value 转成字符串再喂进来）。
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping
from uuid import UUID

from app.models.reconciliation import ReconDiffKind


# ---------------------------------------------------------------------------
# 状态分类（与 OrderStatus 字符串值对齐）
# ---------------------------------------------------------------------------
# 业务侧「应已收款」的订单状态：触发应收 = price > 0
_BUSINESS_PAID_STATUSES: frozenset[str] = frozenset(
    {"accepted", "in_progress", "completed", "reviewed"}
)
# 业务侧「不应有支付流水」的取消/拒单/过期类状态
_BUSINESS_CANCELLED_STATUSES: frozenset[str] = frozenset(
    {
        "cancelled_by_patient",
        "cancelled_by_companion",
        "rejected_by_companion",
        "expired",
    }
)
# 流水侧「视为有效收款」的状态
_PAYMENT_SUCCESS_STATUSES: frozenset[str] = frozenset({"success"})

_ZERO = Decimal("0.00")


# ---------------------------------------------------------------------------
# 数据快照（dataclass，frozen=True 表明纯数据）
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class BusinessSnapshot:
    """订单业务真相：``orders.status`` + ``orders.price`` 的快照。"""

    order_id: UUID
    status: str
    amount: Decimal


@dataclass(frozen=True)
class PaymentSnapshot:
    """流水真相：``payments`` 表里**净额**（pay - refund）后的快照。

    IO 层在喂入前已经 ``SUM(amount * sign)`` 聚合好；``status`` 取最新一条
    流水的状态（用于诊断 ``status_mismatch``）。
    """

    order_id: UUID
    status: str
    amount: Decimal
    provider: str | None = None
    provider_txn_id: str | None = None


@dataclass(frozen=True)
class LedgerSnapshot:
    """账本真相：``wallet_ledger`` 按订单聚合后的净额。"""

    order_id: UUID
    status: str
    amount: Decimal


@dataclass(frozen=True)
class ReconDiff:
    order_id: UUID | None
    kind: ReconDiffKind
    business_amount: Decimal | None = None
    payment_amount: Decimal | None = None
    ledger_amount: Decimal | None = None
    business_status: str | None = None
    payment_status: str | None = None
    ledger_status: str | None = None
    provider: str | None = None
    provider_txn_id: str | None = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _q(amount: Decimal | None) -> Decimal:
    """金额归一到 0.01 精度的 Decimal；None → 0.00。"""
    if amount is None:
        return _ZERO
    if not isinstance(amount, Decimal):  # 防御：避免 float 漏进来
        amount = Decimal(str(amount))
    return amount.quantize(Decimal("0.01"))


def _business_expects_payment(b: BusinessSnapshot) -> bool:
    return b.status in _BUSINESS_PAID_STATUSES and _q(b.amount) > _ZERO


def _business_is_cancelled(b: BusinessSnapshot) -> bool:
    return b.status in _BUSINESS_CANCELLED_STATUSES


def _payment_is_successful(p: PaymentSnapshot) -> bool:
    return p.status in _PAYMENT_SUCCESS_STATUSES and _q(p.amount) > _ZERO


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
def diff_orders(
    business: Mapping[UUID, BusinessSnapshot],
    payments: Mapping[UUID, PaymentSnapshot],
    ledger: Mapping[UUID, LedgerSnapshot],
) -> list[ReconDiff]:
    """计算三源对账差异列表（确定性、无 IO）。"""
    diffs: list[ReconDiff] = []

    # --- Pass 1: 以业务订单为锚点 ---
    for order_id, b in business.items():
        p = payments.get(order_id)
        l = ledger.get(order_id)

        b_amt = _q(b.amount)
        p_amt = _q(p.amount) if p is not None else _ZERO
        l_amt = _q(l.amount) if l is not None else _ZERO

        b_expects = _business_expects_payment(b)
        b_cancel = _business_is_cancelled(b)
        p_ok = p is not None and _payment_is_successful(p)

        # MISSING_PAYMENT：业务应收但无 success 流水
        if b_expects and not p_ok:
            diffs.append(
                ReconDiff(
                    order_id=order_id,
                    kind=ReconDiffKind.missing_payment,
                    business_amount=b_amt,
                    payment_amount=p_amt if p is not None else None,
                    ledger_amount=l_amt if l is not None else None,
                    business_status=b.status,
                    payment_status=p.status if p is not None else None,
                    ledger_status=l.status if l is not None else None,
                    provider=p.provider if p is not None else None,
                    provider_txn_id=p.provider_txn_id if p is not None else None,
                )
            )
            continue  # 同一笔订单，金额/状态 mismatch 不再叠报

        # AMOUNT_MISMATCH：业务期望付款时，三源金额必须相等
        if b_expects:
            if b_amt != p_amt or p_amt != l_amt:
                diffs.append(
                    ReconDiff(
                        order_id=order_id,
                        kind=ReconDiffKind.amount_mismatch,
                        business_amount=b_amt,
                        payment_amount=p_amt,
                        ledger_amount=l_amt,
                        business_status=b.status,
                        payment_status=p.status if p is not None else None,
                        ledger_status=l.status if l is not None else None,
                        provider=p.provider if p is not None else None,
                        provider_txn_id=(
                            p.provider_txn_id if p is not None else None
                        ),
                    )
                )
                continue

        # 已 cancelled 业务但流水侧仍有 success 净额（且未退干净）→ ORPHAN_PAYMENT
        if b_cancel and p_ok and p_amt > _ZERO:
            diffs.append(
                ReconDiff(
                    order_id=order_id,
                    kind=ReconDiffKind.orphan_payment,
                    business_amount=b_amt,
                    payment_amount=p_amt,
                    ledger_amount=l_amt if l is not None else None,
                    business_status=b.status,
                    payment_status=p.status,
                    ledger_status=l.status if l is not None else None,
                    provider=p.provider,
                    provider_txn_id=p.provider_txn_id,
                )
            )
            continue

        # STATUS_MISMATCH：金额一致但相位错位
        # 1) 业务已取消但账本仍有正余额（应退未退）
        if b_cancel and l is not None and l_amt > _ZERO:
            diffs.append(
                ReconDiff(
                    order_id=order_id,
                    kind=ReconDiffKind.status_mismatch,
                    business_amount=b_amt,
                    payment_amount=p_amt if p is not None else None,
                    ledger_amount=l_amt,
                    business_status=b.status,
                    payment_status=p.status if p is not None else None,
                    ledger_status=l.status,
                    provider=p.provider if p is not None else None,
                    provider_txn_id=p.provider_txn_id if p is not None else None,
                )
            )
            continue

        # 2) 业务应收金额 > 0、流水状态非 success（pending / failed）但金额对齐
        if (
            b_expects
            and p is not None
            and not p_ok
            and b_amt == p_amt
            and p_amt == l_amt
        ):
            # 已被 missing_payment 路径吃掉；此处不会到达。保留分支占位。
            pass

        # 3) 账本与流水金额不一致（业务非应收场景，例如三方均 0 但某一项 > 0）
        if not b_expects and not b_cancel:
            if (p is not None and p_amt > _ZERO) or (
                l is not None and l_amt > _ZERO
            ):
                diffs.append(
                    ReconDiff(
                        order_id=order_id,
                        kind=ReconDiffKind.status_mismatch,
                        business_amount=b_amt,
                        payment_amount=p_amt if p is not None else None,
                        ledger_amount=l_amt if l is not None else None,
                        business_status=b.status,
                        payment_status=p.status if p is not None else None,
                        ledger_status=l.status if l is not None else None,
                        provider=p.provider if p is not None else None,
                        provider_txn_id=(
                            p.provider_txn_id if p is not None else None
                        ),
                    )
                )

    # --- Pass 2: 以流水为锚点，找业务侧不存在的孤儿流水 ---
    for order_id, p in payments.items():
        if order_id in business:
            continue
        if not _payment_is_successful(p):
            continue
        l = ledger.get(order_id)
        diffs.append(
            ReconDiff(
                order_id=order_id,
                kind=ReconDiffKind.orphan_payment,
                business_amount=None,
                payment_amount=_q(p.amount),
                ledger_amount=_q(l.amount) if l is not None else None,
                business_status=None,
                payment_status=p.status,
                ledger_status=l.status if l is not None else None,
                provider=p.provider,
                provider_txn_id=p.provider_txn_id,
            )
        )

    # --- Pass 3: 以账本为锚点，找业务+流水都缺席但账本有钱的脏数据 ---
    for order_id, l in ledger.items():
        if order_id in business or order_id in payments:
            continue
        if _q(l.amount) == _ZERO:
            continue
        diffs.append(
            ReconDiff(
                order_id=order_id,
                kind=ReconDiffKind.amount_mismatch,
                business_amount=None,
                payment_amount=None,
                ledger_amount=_q(l.amount),
                business_status=None,
                payment_status=None,
                ledger_status=l.status,
            )
        )

    diffs.sort(key=lambda d: (str(d.order_id) if d.order_id else "", d.kind.value))
    return diffs
