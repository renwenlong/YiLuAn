"""Schemas for admin cache invalidation endpoint.

S3-DEV-005-CACHE-INVALIDATE — admin manual cache invalidation API.

ADR-0048 §6 / design doc ``S3-trust-precheck-ui.md`` line 224 + PRD-001 v1.4 §F8.

The endpoint is the **manual** counterpart to the automatic
:class:`OrderPrecheckAggregator` 4-hook flow (S3-DEV-003-PRECHECK-BACKEND).
Admins (super only) call it when they need to force a cache eviction +
recompute outside the normal trigger paths (e.g. mass-update remediation
or staging hot-fix).

This task ships the **stub-edition**: the endpoint is fully implemented
(ABAC + audit + rate limit), but ``OrderPrecheckAggregator.evaluate /
_redis_set / _ws_broadcast`` raise :class:`NotImplementedError`. The
endpoint therefore returns **501 Not Implemented** rather than 200; the
PRECHECK-BACKEND task fills in the aggregator and the same endpoint
flips to 200 automatically (no API contract change).
"""

from __future__ import annotations

from typing import Literal, get_args
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Hard-coded card names the aggregator knows about. Keep in sync with
# design doc S3-trust-precheck-ui.md §3 — 4 "信任卡" cards: companion
# cert, insurance, prep package, contract. Aggregator packs all 4 into
# one cache key ``precheck:order:{order_id}``; the ``cards`` param is
# stored in the audit row for per-card traceability (魈 Q4 #3) but does
# not change the cache key shape.
#
# Pydantic ``Literal`` 在 ``cards: list[CardName] | None`` 上自动校验:
# 任何 not-in-set value → 422 ValidationError. 这是刻晴 PR #250 r1 红线
# 修法 (避免 admin 拼错 'companion_certs' 落 audit + 后续 evaluate 假命中).
CardName = Literal["companion_cert", "insurance", "prep_package", "contract"]

# Frozen set 暴露给 endpoint / test 在 docstring / log / 异常 message 里
# 列举合法 card 名 (不参与 schema 校验, 校验靠 Literal). 用 ``get_args``
# 从 Literal 取 single source of truth, 避免 list 维护漂移.
_ALL_KNOWN_CARDS: frozenset[str] = frozenset(get_args(CardName))


class CacheInvalidateRequest(BaseModel):
    """Body for ``POST /api/v1/admin/cache/invalidate``.

    Fields:

    * ``order_id`` — required UUID of the order whose precheck summary
      cache should be invalidated.
    * ``cards`` — optional list of card names limited to
      :data:`CardName` (Literal-enforced 422 on typo). Defaults to all
      4 cards when omitted. Stored verbatim in the audit row so per-card
      remediation drives can be reconstructed; aggregator still packs
      every card into the single ``precheck:order:{order_id}`` key.
    """

    model_config = ConfigDict(extra="forbid")

    order_id: UUID = Field(
        ...,
        description="订单 UUID。aggregator 用此组装 cache key precheck:order:{order_id}。",
    )
    cards: list[CardName] | None = Field(
        default=None,
        description=(
            "可选, 待失效的卡列表 (companion_cert / insurance / prep_package / "
            "contract)。omit 视为 all 4。仅落 AdminAuditLog, 不改 cache key 形状。"
            "Pydantic Literal 校验, 拼错任一 card → 422。"
        ),
    )


class CacheInvalidateResponse(BaseModel):
    """Response body for the endpoint.

    Returns 200 once :class:`OrderPrecheckAggregator` is fully implemented
    by PRECHECK-BACKEND. Until then, the endpoint raises 501 from the
    stub layer (this schema is unused on the stub path but ships in the
    OpenAPI for forward compatibility).
    """

    model_config = ConfigDict(extra="forbid")

    invalidated_keys: list[str] = Field(
        ...,
        description=(
            "aggregator 执行 redis DEL 的 key 列表 "
            "(通常单元素 precheck:order:{order_id})。"
        ),
    )
    broadcast: bool = Field(
        ...,
        description=(
            "WS broadcast 是否完成 "
            "(precheck.status.updated 推 user + companion, "
            "envelope 含 cert 状态语义)。"
        ),
    )
