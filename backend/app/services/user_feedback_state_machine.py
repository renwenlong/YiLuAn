"""User feedback state machine (S3-DEV-004-FEEDBACK-DOMAIN / ADR-0049 §4.1).

# Why a dedicated module

ADR-0049 §2.1 + ADR-0041 状态机解耦原则: 反馈状态独立于订单状态,
``OrderStateMachine`` 不感知反馈生命周期, 反馈状态不驱动订单状态.
独立模块避免反馈状态泄漏到核心订单状态机.

# Transition table (ADR-0049 §4.1 ground truth, 8 legal edges, 5 states)

```
pending             ──→ in_review                (admin_start_review)
pending             ──→ rejected                 (admin_reject_invalid)

in_review           ──→ resolved                 (admin_resolve)
in_review           ──→ rejected                 (admin_reject_invalid)

resolved            ──→ closed                   (user_accept_or_timeout)
resolved            ──→ in_review                (user_append_feedback)

rejected            ──→ in_review                (user_append_feedback)

closed              ──→ in_review                (user_append_feedback_within_30d)
                                                  — 仅 30d 窗口内允许, 超出 HTTP 410 Gone

# 无 hard terminal (与 ContractStateMachine 不同):
# closed/rejected 都可被 user_append 重新激活回 in_review.
# closed > 30d 由 endpoint 层 (S3-DEV-004-FEEDBACK-API) HTTP 410 拒.
```

# Append 边权限规则 (ADR-0049 §4.1, 刻晴 review #6 amend)

| 当前状态 | user_append 允许? | 原因 |
|---------|-------------------|------|
| ``pending`` | ❌ | admin 未触达, 用户应直接编辑首条 |
| ``in_review`` | ❌ | admin 处理中, 防状态机振荡 |
| ``resolved`` | ✅ → ``in_review`` | 重新激活 |
| ``rejected`` | ✅ → ``in_review`` | 申诉/补证 |
| ``closed`` | ✅ → ``in_review`` 仅 ≤30d | 防历史反馈反复点火 |

本 module 提供 :func:`can_user_append` predicate; 30d 窗口判断需 endpoint
层传入 ``closed_at`` 与 ``now()``, 由 :func:`can_user_append_when_closed`
计算; 路由层负责 HTTP 410.

# 与 ContractStateMachine 的取舍差异

- ContractStateMachine: ``manually_invalidated`` hard terminal
- UserFeedbackStateMachine: 无 hard terminal, user_append 可激活任何 closed/rejected

原因: 用户反馈是用户体验通道, 应保留补充权利; 而合同 immutable 是 WORM 法律
约束, 一经作废永久作废.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Final

from app.models.user_feedback import CLOSED_APPEND_WINDOW_DAYS, FeedbackStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transition table — frozenset single source of truth
# ---------------------------------------------------------------------------


_LEGAL_TRANSITIONS: Final[frozenset[tuple[FeedbackStatus, FeedbackStatus]]] = frozenset(
    {
        # pending 出边
        (FeedbackStatus.pending, FeedbackStatus.in_review),
        (FeedbackStatus.pending, FeedbackStatus.rejected),
        # in_review 出边
        (FeedbackStatus.in_review, FeedbackStatus.resolved),
        (FeedbackStatus.in_review, FeedbackStatus.rejected),
        # resolved 出边 — append 重激活
        (FeedbackStatus.resolved, FeedbackStatus.closed),
        (FeedbackStatus.resolved, FeedbackStatus.in_review),
        # rejected 出边 — append 申诉
        (FeedbackStatus.rejected, FeedbackStatus.in_review),
        # closed 出边 — 30d 内 append 复活 (窗口判断在 can_user_append_when_closed)
        (FeedbackStatus.closed, FeedbackStatus.in_review),
    }
)
"""8 legal (from, to) transitions; pinned by sentinel test."""


# 无 hard terminal — 与 ContractStateMachine 故意不同
_HARD_TERMINAL: Final[frozenset[FeedbackStatus]] = frozenset()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidFeedbackStateTransitionError(ValueError):
    """Raised when caller tries to apply a (from, to) not in legal table."""


class FeedbackAppendWindowExpiredError(ValueError):
    """Raised when user attempts to append to a closed feedback past 30d window.

    Endpoint 层应捕获并返回 HTTP 410 Gone (ADR-0049 §4.1).
    """


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def is_terminal(status: FeedbackStatus) -> bool:
    """Return True if ``status`` is a hard terminal.

    UserFeedback 无 hard terminal (与 ContractStateMachine 不同) — closed/rejected
    都可被 user_append 复活. 此函数恒返 False, 保留与其他状态机签名一致供
    polymorphic 调用方使用.
    """
    return status in _HARD_TERMINAL


def is_legal_transition(
    from_status: FeedbackStatus, to_status: FeedbackStatus
) -> bool:
    """Pure predicate — check if (from, to) is in the legal table.

    Does **not** check 30d window for closed → in_review; use
    :func:`can_user_append_when_closed` for that.
    """
    return (from_status, to_status) in _LEGAL_TRANSITIONS


def legal_targets(from_status: FeedbackStatus) -> frozenset[FeedbackStatus]:
    """All legal targets from ``from_status``."""
    return frozenset(to for (frm, to) in _LEGAL_TRANSITIONS if frm == from_status)


def can_user_append(from_status: FeedbackStatus) -> bool:
    """Whether user_append is allowed from ``from_status`` (ADR-0049 §4.1).

    ``pending`` / ``in_review`` → False (用户应直接编辑首条 / 防状态机振荡)
    ``resolved`` / ``rejected`` → True
    ``closed`` → True 仅 30d 内 (具体由 :func:`can_user_append_when_closed`)
    """
    return from_status in {
        FeedbackStatus.resolved,
        FeedbackStatus.rejected,
        FeedbackStatus.closed,
    }


def can_user_append_when_closed(
    *, closed_at: datetime, now: datetime | None = None
) -> bool:
    """Whether user_append is allowed for closed feedback (30d window).

    Args:
        closed_at: feedback.closed_at 时间戳 (timezone-aware)
        now: 当前时间 (默认 utcnow), 主要供测试注入

    Returns:
        True 若 (now - closed_at) ≤ 30d; False 否则.

    Raises:
        ValueError: 若 closed_at 不带 tzinfo (防 naive datetime 误判)
    """
    if closed_at.tzinfo is None:
        raise ValueError(
            "closed_at must be timezone-aware datetime; "
            "got naive datetime which is ambiguous"
        )
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("now must be timezone-aware if provided explicitly")
    window = timedelta(days=CLOSED_APPEND_WINDOW_DAYS)
    return (current - closed_at) <= window


# ---------------------------------------------------------------------------
# Public guard (caller invokes before mutating .status)
# ---------------------------------------------------------------------------


def assert_transition(
    *,
    from_status: FeedbackStatus,
    to_status: FeedbackStatus,
) -> None:
    """Legal-table guard.

    Use this as a barrier before any caller mutates ``feedback.status``:

        assert_transition(from_status=feedback.status, to_status=new_status)
        feedback.status = new_status

    Note: closed → in_review 的 30d 窗口由 endpoint 层用
    :func:`can_user_append_when_closed` 单独把关; 本 guard 只看 legal table,
    不掺时间逻辑 (单一职责).

    Raises:
        InvalidFeedbackStateTransitionError: illegal (from, to)
    """
    if not is_legal_transition(from_status, to_status):
        legal = sorted(s.value for s in legal_targets(from_status))
        raise InvalidFeedbackStateTransitionError(
            f"illegal feedback status transition: "
            f"{from_status.value} → {to_status.value}; "
            f"legal targets from {from_status.value}: {legal}"
        )


def assert_user_append_allowed(
    *,
    from_status: FeedbackStatus,
    closed_at: datetime | None = None,
    now: datetime | None = None,
) -> None:
    """Compound guard: append permission + closed 30d window.

    1. Check :func:`can_user_append` based on ``from_status``
    2. If ``from_status == closed``, additionally check 30d window via
       :func:`can_user_append_when_closed`

    Args:
        from_status: feedback.status 当前态
        closed_at: 若 from_status == closed, 必须提供 feedback.closed_at
        now: 测试注入

    Raises:
        InvalidFeedbackStateTransitionError: from_status 不允许 append
            (pending / in_review)
        FeedbackAppendWindowExpiredError: closed 状态但超 30d
        ValueError: closed 状态但未提供 closed_at
    """
    if not can_user_append(from_status):
        raise InvalidFeedbackStateTransitionError(
            f"user_append not allowed from {from_status.value}: "
            f"pending / in_review 不允许 append "
            f"(用户应直接编辑首条 / admin 处理中防状态机振荡)"
        )
    if from_status == FeedbackStatus.closed:
        if closed_at is None:
            raise ValueError(
                "closed_at must be provided when from_status is 'closed' "
                "to evaluate 30d append window"
            )
        if not can_user_append_when_closed(closed_at=closed_at, now=now):
            raise FeedbackAppendWindowExpiredError(
                f"user_append on closed feedback expired: "
                f"closed_at={closed_at.isoformat()}, "
                f"window={CLOSED_APPEND_WINDOW_DAYS}d. "
                f"Endpoint should return HTTP 410 Gone."
            )
