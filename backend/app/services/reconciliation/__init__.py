"""[ADR-0032 / TD-MONEY-01 M1] 资金对账纯函数模块。

核心入口：``diff_orders``。三个入参为纯数据快照（dataclass），输出确定性的
``ReconDiff`` 列表。**不持 Session、不发 IO、不出现 await**。
"""
from app.services.reconciliation.diff import (
    BusinessSnapshot,
    LedgerSnapshot,
    PaymentSnapshot,
    ReconDiff,
    diff_orders,
)
from app.models.reconciliation import ReconDiffKind

__all__ = [
    "BusinessSnapshot",
    "PaymentSnapshot",
    "LedgerSnapshot",
    "ReconDiff",
    "ReconDiffKind",
    "diff_orders",
]
