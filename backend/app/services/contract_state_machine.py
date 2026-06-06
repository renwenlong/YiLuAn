"""Contract state machine (S3-DEV-001-CONTRACT-DOMAIN / ADR-0047 §4).

# Why a dedicated module

ADR-0047 §4 拒污染 ``OrderStateMachine``: contract lifecycle is independent
from order lifecycle. 一个订单可以 cancelled 但其合同仍然 active (合同生效
后退款不撤回合同, 只走 manually_invalidated 留痕)。独立模块避免合同状态
泄漏到核心订单状态机。

# Transition table (14 legal edges, 6 states, ADR-0047 §3.1 ground truth)

```
pending_generation ──→ generating               (cron pickup)
pending_generation ──→ manually_invalidated     (admin 灰度回滚)

generating          ──→ active                  (put_contract 成功)
generating          ──→ generation_failed       (put_contract 失败)
generating          ──→ manually_invalidated    (admin 中止)

active              ──→ manually_invalidated    (灰度作废 / 客服)

generation_failed   ──→ generating              (retry pickup, retry_count < 3)
generation_failed   ──→ generation_permanently_failed  (retry_count >= 3, admin alert)
generation_failed   ──→ manually_invalidated    (admin 主动放弃)

generation_permanently_failed ──→ manually_invalidated  (admin 收尾)

# 终态 (无 outgoing):
manually_invalidated ─×→
```

`active`, `generation_permanently_failed` 不是 hard terminal — 仍可被 admin
强制转 manually_invalidated 留痕。
`manually_invalidated` 是唯一 hard terminal (审计已落, 不可再变).

# Retry guard (魈 08:25 AC#3 + AC#5)

`generation_failed → generation_permanently_failed` 必须 retry_count >= 3,
否则 RAISE :class:`InvalidContractStateTransitionError`. 这是 ADR-0046 §3.4
"3 次重试" 合约的应用层兜底 (DB 层无此约束 — trigger 只管 immutable 字段).

# Invalidation metadata (AC#5 同款 INSURANCE)

转 ``manually_invalidated`` 必须同时提供:
- ``invalidation_reason`` (非空, NFKC normalized)
- ``invalidated_by_admin_id`` (非空)

否则 :class:`ContractInvalidationMetadataMissingError`.
"""

from __future__ import annotations

import logging
import unicodedata
import uuid
from typing import Final

from app.models.service_contract import ContractStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transition table — frozenset single source of truth
# ---------------------------------------------------------------------------


_LEGAL_TRANSITIONS: Final[frozenset[tuple[ContractStatus, ContractStatus]]] = frozenset(
    {
        # pending_generation 出边
        (ContractStatus.pending_generation, ContractStatus.generating),
        (
            ContractStatus.pending_generation,
            ContractStatus.manually_invalidated,
        ),
        # generating 出边
        (ContractStatus.generating, ContractStatus.active),
        (ContractStatus.generating, ContractStatus.generation_failed),
        (ContractStatus.generating, ContractStatus.manually_invalidated),
        # active 出边
        (ContractStatus.active, ContractStatus.manually_invalidated),
        # generation_failed 出边 (3 transitions, retry guard on
        # generation_permanently_failed enforced separately)
        (ContractStatus.generation_failed, ContractStatus.generating),
        (
            ContractStatus.generation_failed,
            ContractStatus.generation_permanently_failed,
        ),
        (
            ContractStatus.generation_failed,
            ContractStatus.manually_invalidated,
        ),
        # generation_permanently_failed 出边 (admin 收尾)
        (
            ContractStatus.generation_permanently_failed,
            ContractStatus.manually_invalidated,
        ),
        # manually_invalidated 是 hard terminal
    }
)
"""10 legal (from, to) transitions; pinned by sentinel test."""


_HARD_TERMINAL: Final[frozenset[ContractStatus]] = frozenset({ContractStatus.manually_invalidated})

# Max retries before permanent failure (ADR-0046 §3.4)
MAX_RETRY_COUNT: Final[int] = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class InvalidContractStateTransitionError(ValueError):
    """Raised when caller tries to apply a (from, to) not in legal table,
    or when retry-guard rejects transition to permanently_failed.
    """


class ContractInvalidationMetadataMissingError(ValueError):
    """Raised when transition to ``manually_invalidated`` lacks metadata.

    AC#5 强约束: ``invalidation_reason`` + ``invalidated_by_admin_id`` 必填.
    """


# ---------------------------------------------------------------------------
# Public predicates
# ---------------------------------------------------------------------------


def is_terminal(status: ContractStatus) -> bool:
    """Return True if ``status`` is a hard terminal (no outgoing edges)."""
    return status in _HARD_TERMINAL


def is_legal_transition(from_status: ContractStatus, to_status: ContractStatus) -> bool:
    """Pure predicate — check if (from, to) is in the legal table.

    Does **not** check retry-guard for permanently_failed; use
    :func:`assert_transition` for the full check.
    """
    return (from_status, to_status) in _LEGAL_TRANSITIONS


def legal_targets(from_status: ContractStatus) -> frozenset[ContractStatus]:
    """All legal targets from ``from_status`` (ignoring retry guard)."""
    return frozenset(to for (frm, to) in _LEGAL_TRANSITIONS if frm == from_status)


# ---------------------------------------------------------------------------
# Public guards (caller invokes before mutating .status)
# ---------------------------------------------------------------------------


def assert_transition(
    *,
    from_status: ContractStatus,
    to_status: ContractStatus,
    retry_count: int,
) -> None:
    """Full guard: legal-table check + retry-count check for permanent failure.

    Use this as a barrier before any caller mutates ``record.status``:

        assert_transition(
            from_status=record.status,
            to_status=new_status,
            retry_count=record.retry_count,
        )
        record.status = new_status

    Raises:
        InvalidContractStateTransitionError: illegal (from, to) OR
            retry_count < MAX for transition to permanently_failed
    """
    if not is_legal_transition(from_status, to_status):
        legal = sorted(s.value for s in legal_targets(from_status))
        raise InvalidContractStateTransitionError(
            f"illegal contract status transition: "
            f"{from_status.value} → {to_status.value}; "
            f"legal targets from {from_status.value}: {legal}"
        )
    # Retry guard: only allow permanently_failed when retry_count exhausted
    if to_status == ContractStatus.generation_permanently_failed and retry_count < MAX_RETRY_COUNT:
        raise InvalidContractStateTransitionError(
            f"cannot transition to generation_permanently_failed: "
            f"retry_count={retry_count} < MAX_RETRY_COUNT={MAX_RETRY_COUNT}; "
            f"caller must exhaust retries first"
        )


def assert_invalidation_metadata(
    *,
    invalidation_reason: str | None,
    invalidated_by_admin_id: uuid.UUID | None,
) -> None:
    """Raise if either field missing/empty when target is manually_invalidated.

    AC#5 audit completeness. Whitespace-only reason rejected.
    """
    if not invalidation_reason or not invalidation_reason.strip():
        raise ContractInvalidationMetadataMissingError(
            "invalidation_reason required for manually_invalidated transition"
        )
    if invalidated_by_admin_id is None:
        raise ContractInvalidationMetadataMissingError(
            "invalidated_by_admin_id required for manually_invalidated transition"
        )


# ---------------------------------------------------------------------------
# Patient name normalization (AC#7 — caller must invoke before hash)
# ---------------------------------------------------------------------------


def normalize_patient_name(raw_name: str) -> str:
    """NFKC + strip (AC#7 — required before calling compute_patient_pseudonym_hash).

    Defends against same patient appearing with different whitespace
    representations from different sources (微信 / iOS / admin):

        normalize_patient_name("张三 ") == normalize_patient_name(" 张三")
                                       == normalize_patient_name("张\u3000三".replace("三", " 三"))

    Without normalization: same person → different pseudonym hash →
    different contract_hash → "duplicate" contract rejected on UNIQUE.

    NFKC was chosen over NFC because:
    - Some Chinese name inputs include full-width ASCII space (U+3000)
      between characters when copy-pasted from forms; NFC keeps these,
      NFKC folds to ASCII space (U+0020) before .strip() removes them
    - NFKC is the standard for "compatible decomposition + canonical
      composition" — what people expect for visual equivalence

    Raises:
        ValueError: raw_name is None or whitespace-only after normalize
    """
    if raw_name is None:
        raise ValueError("patient name cannot be None")
    normalized = unicodedata.normalize("NFKC", raw_name).strip()
    if not normalized:
        raise ValueError("patient name is empty after NFKC + strip")
    return normalized


__all__ = [
    "MAX_RETRY_COUNT",
    "ContractInvalidationMetadataMissingError",
    "InvalidContractStateTransitionError",
    "assert_invalidation_metadata",
    "assert_transition",
    "is_legal_transition",
    "is_terminal",
    "legal_targets",
    "normalize_patient_name",
]
