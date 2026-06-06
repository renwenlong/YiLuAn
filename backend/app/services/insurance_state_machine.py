"""Insurance order state machine (S3-DEV-001-INSURANCE-DOMAIN / ADR-0047 §4).

# Why a dedicated state machine module

ADR-0047 §4 拒污染 ``OrderStateMachine``: insurance lifecycle is
independent from order lifecycle (一个订单可以 cancelled 但其保单
manually_invalidated 留痕, 不影响 OrderStatus 转 cancelled)。
独立类避免 service_type-specific 状态泄漏到核心 Order 状态机。

# Transition table

```
pending_issue ──→ active                (vendor issue OK)
pending_issue ──→ issue_failed          (vendor API 失败)
pending_issue ──→ cancelled             (订单未付款就取消 → 保险直接 cancel)
pending_issue ──→ manually_invalidated  (admin 手动作废)

active        ──→ expired               (保障期到自然过期)
active        ──→ cancelled             (订单 cancel/refund 触发同步作废)
active        ──→ manually_invalidated  (admin 手动作废)

issue_failed  ──→ active                (补偿 cron 重试成功)
issue_failed  ──→ cancelled             (订单取消, 放弃重试)
issue_failed  ──→ manually_invalidated  (admin 手动作废终止补偿)

# 终态 (无 outgoing edge):
expired               ─×→
cancelled             ─×→
manually_invalidated  ─×→
```

# manually_invalidated 留痕约束 (ADR-0047 §3.3 + AC#5)

转 ``manually_invalidated`` 必须同时提供:
- ``invalidation_reason`` (非空)
- ``invalidated_by_admin_id`` (非空)

否则 :class:`InsuranceInvalidationMetadataMissingError`。这是 audit 强制 —
即使 admin UI 漏字段, service 层兜底拒绝写库, 保证审计完整。
"""

from __future__ import annotations

import logging
import uuid
from typing import Final

from app.models.service_insurance_record import InsuranceStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transition table — single source of truth for legal transitions
# ---------------------------------------------------------------------------


_LEGAL_TRANSITIONS: Final[frozenset[tuple[InsuranceStatus, InsuranceStatus]]] = frozenset(
    {
        # pending_issue 出边
        (InsuranceStatus.pending_issue, InsuranceStatus.active),
        (InsuranceStatus.pending_issue, InsuranceStatus.issue_failed),
        (InsuranceStatus.pending_issue, InsuranceStatus.cancelled),
        (InsuranceStatus.pending_issue, InsuranceStatus.manually_invalidated),
        # active 出边
        (InsuranceStatus.active, InsuranceStatus.expired),
        (InsuranceStatus.active, InsuranceStatus.cancelled),
        (InsuranceStatus.active, InsuranceStatus.manually_invalidated),
        # issue_failed 出边
        (InsuranceStatus.issue_failed, InsuranceStatus.active),
        (InsuranceStatus.issue_failed, InsuranceStatus.cancelled),
        (InsuranceStatus.issue_failed, InsuranceStatus.manually_invalidated),
        # expired / cancelled / manually_invalidated 是终态 — 无 outgoing edges
    }
)
"""Frozen set of all legal (from, to) transitions; len == 10."""


# Terminal states — no outgoing transitions
_TERMINAL_STATES: Final[frozenset[InsuranceStatus]] = frozenset(
    {
        InsuranceStatus.expired,
        InsuranceStatus.cancelled,
        InsuranceStatus.manually_invalidated,
    }
)


# Max retries before permanent failure (ADR-0047 §3.3 + ADR-0046 §3.4 同款 3 次)
MAX_RETRY_COUNT: Final[int] = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidInsuranceTransitionError(ValueError):
    """Raised when caller tries to apply a (from, to) not in transition table.

    Caller surface: ``InsuranceService`` translates this to a 409 Conflict;
    state machine guards never silently flip status.
    """


class InsuranceInvalidationMetadataMissingError(ValueError):
    """Raised when transition to ``manually_invalidated`` lacks metadata.

    AC#5 强约束: ``invalidation_reason`` + ``invalidated_by_admin_id`` 必填。
    """


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_terminal(status: InsuranceStatus) -> bool:
    """Return True if ``status`` has no legal outgoing transitions."""
    return status in _TERMINAL_STATES


def is_legal_transition(from_status: InsuranceStatus, to_status: InsuranceStatus) -> bool:
    """Pure predicate — check if (from, to) is in the legal table."""
    return (from_status, to_status) in _LEGAL_TRANSITIONS


def legal_targets(from_status: InsuranceStatus) -> frozenset[InsuranceStatus]:
    """All legal ``to`` states reachable from ``from_status`` in one step.

    Returns empty frozenset for terminal states.
    """
    return frozenset(to for (frm, to) in _LEGAL_TRANSITIONS if frm == from_status)


def assert_transition_legal(from_status: InsuranceStatus, to_status: InsuranceStatus) -> None:
    """Raise :class:`InvalidInsuranceTransitionError` if illegal.

    Use this as a guard inside any caller that mutates ``status``:

        assert_transition_legal(record.status, new_status)
        record.status = new_status
    """
    if not is_legal_transition(from_status, to_status):
        legal = sorted(s.value for s in legal_targets(from_status))
        raise InvalidInsuranceTransitionError(
            f"illegal insurance status transition: "
            f"{from_status.value} → {to_status.value}; "
            f"legal targets from {from_status.value}: {legal}"
        )


def assert_invalidation_metadata(
    *,
    invalidation_reason: str | None,
    invalidated_by_admin_id: uuid.UUID | None,
) -> None:
    """Raise if either field is missing/empty (AC#5 audit completeness).

    Only called when target status is ``manually_invalidated``. The
    automatic ``cancelled`` path (order cancel/refund cascade) does NOT
    require this metadata — it has its own audit trail via the cancel
    order log.
    """
    if not invalidation_reason or not invalidation_reason.strip():
        raise InsuranceInvalidationMetadataMissingError(
            "invalidation_reason required for manually_invalidated transition"
        )
    if invalidated_by_admin_id is None:
        raise InsuranceInvalidationMetadataMissingError(
            "invalidated_by_admin_id required for manually_invalidated transition"
        )


__all__ = [
    "MAX_RETRY_COUNT",
    "InsuranceInvalidationMetadataMissingError",
    "InvalidInsuranceTransitionError",
    "assert_invalidation_metadata",
    "assert_transition_legal",
    "is_legal_transition",
    "is_terminal",
    "legal_targets",
]
