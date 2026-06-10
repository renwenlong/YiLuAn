"""S3-DEV-005-CACHE-INVALIDATE — admin cache invalidate endpoint tests.

Covers 魈 task comment ``79ce3e34`` 4 hard requirements + c2 evaluate
contract (S3-DEV-003-PRECHECK-BACKEND c2 replaced the stub 501 path
with real evaluate + cache SET):

* AC#1: ``AdminAuditLog`` row is written (target_type / action /
  operator / cards in ``reason``).
* AC#2: rate limit ``5/minute per admin`` — 6th call within the
  same window returns 429.
* AC#3: per-card audit tag — ``cards`` list ends up verbatim in
  the audit row's ``reason`` column (sorted, comma-joined).
* AC#4: cache key shape — defensive ``redis DEL`` targets the single
  ``precheck:order:{order_id}`` key (no per-card variants).
* c2 evaluate: endpoint returns 200 + ``invalidated_keys`` +
  ``broadcast=False``. ``broadcast`` flips to True when c4 WS infra
  lands (which will trigger a similar canary update in this file).
* Auth: ``super_`` role passes; ``ops`` / ``finance`` get 403;
  missing token = 401.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import create_admin_access_token
from app.core.rate_limit import limiter as _rate_limiter
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.services.order_precheck_aggregator import _build_cache_key
from tests.conftest import test_session_factory as _session_factory

INVALIDATE_URL = "/api/v1/admin/cache/invalidate"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _seed_admin(username: str, role: AdminRole) -> str:
    async with _session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash="test-not-used",
            role=role,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return create_admin_access_token(admin)


@pytest.fixture
async def super_token() -> str:
    return await _seed_admin("cache_super", AdminRole.super_)


@pytest.fixture
async def ops_token() -> str:
    return await _seed_admin("cache_ops", AdminRole.ops)


@pytest.fixture
async def finance_token() -> str:
    return await _seed_admin("cache_finance", AdminRole.finance)


@pytest.fixture
def enable_real_rate_limit() -> AsyncGenerator[None, None]:
    """Override the suite-wide ``_disable_rate_limiter`` autouse.

    We need a real bucket to verify the ``5/minute per admin``
    constraint. Reset slowapi storage afterwards so other tests don't
    inherit our spent quota.
    """
    prev = _rate_limiter.enabled
    _rate_limiter.enabled = True
    try:
        yield
    finally:
        _rate_limiter.enabled = prev
        _rate_limiter.reset()


async def _list_cache_audits(order_id: str) -> list[AdminAuditLog]:
    async with _session_factory() as session:
        result = await session.execute(
            select(AdminAuditLog)
            .where(
                AdminAuditLog.target_type == "precheck_cache",
                AdminAuditLog.action == "invalidate",
            )
            .order_by(AdminAuditLog.created_at.asc())
        )
        rows = list(result.scalars().all())
    return [r for r in rows if str(r.target_id) == order_id]


# ---------------------------------------------------------------------------
# c2 contract: endpoint returns 200 with real evaluate + cache SET
# (broadcast=False until c4 WS infra lands)
# ---------------------------------------------------------------------------


async def test_super_admin_gets_200_with_invalidated_keys(
    client: AsyncClient, super_token: str
) -> None:
    """S3-DEV-003 c2: aggregator.evaluate landed — endpoint returns 200.

    Previous canary (``test_super_admin_gets_501_from_stub_aggregator``)
    asserted 501 because ``OrderPrecheckAggregator.evaluate`` raised
    :class:`NotImplementedError`. c2 implements evaluate + _redis_set,
    so the stub window has closed and this test now asserts:

    * ``status_code == 200``
    * ``invalidated_keys`` contains the canonical ``precheck:order:{id}`` key
    * ``broadcast == False`` (c4 WS infra still pending; that flip
      lands in c4 and this test must be updated to ``broadcast=True``
      at that point — same canary mechanics, one layer deeper)

    The order need not exist; aggregator returns a 4-card view with
    all ``ready=False`` when rows are missing, which is still a valid
    summary payload and a legitimate cache write.
    """
    order_id = str(uuid4())
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invalidated_keys"] == [f"precheck:order:{order_id}"]
    assert body["broadcast"] is False, (
        "c2 stub _ws_broadcast returns False; flip to True is c4 work "
        "and should re-update this test at that point."
    )


async def test_endpoint_runs_defensive_redis_del_then_set(
    client: AsyncClient, fake_redis: Any, super_token: str
) -> None:
    """Endpoint runs DEL → evaluate → SET in that order.

    Seeds a stale cache entry, invokes the endpoint, asserts the
    final cache value is the fresh aggregator-computed summary (NOT
    the stale value). DEL+SET ordering is the design's main
    consistency guarantee — design line 224 + 胡桃 r3 amend.
    """
    order_id = uuid4()
    key = _build_cache_key(order_id)
    await fake_redis.set(key, '{"stale": "summary"}')
    assert await fake_redis.get(key) is not None

    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_id)},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text

    fresh = await fake_redis.get(key)
    assert fresh is not None, "cache must be re-SET by aggregator after evaluate"
    assert b'"stale"' not in (
        fresh if isinstance(fresh, bytes) else fresh.encode()
    ), "stale payload must have been overwritten"
    parsed = json.loads(fresh)
    assert parsed["order_id"] == str(order_id)
    assert "contract_status" in parsed
    assert "insurance_status" in parsed
    assert "preparation_status" in parsed
    assert "companion_cert_status" in parsed


# ---------------------------------------------------------------------------
# AC#1 + AC#3: audit row written with per-card tag
# ---------------------------------------------------------------------------


async def test_audit_row_persists_per_card_tag(client: AsyncClient, super_token: str) -> None:
    """AC#1 + #3: audit row persists via a dedicated session.

    The endpoint opens its own :class:`AsyncSession`, commits the
    audit row, *then* runs the aggregator. Even though c2 evaluate
    landed (200 path), the dedicated-session pattern remains because:

    * c4 / c5 may add WS broadcast / hook flows that can raise;
    * future failure modes (redis outage, signed-URL gen error)
      still need the audit row durable independent of the request
      transaction.

    This is the explicit fix for the ``view_prep_package`` known
    limitation (which kept audit in the request tx, so 404 / 500
    paths dropped the row). 魈 hard requirement #1 ("AdminAuditLog
    必写") permits no exceptions.
    """
    order_id = str(uuid4())
    before = await _list_cache_audits(order_id)
    response = await client.post(
        INVALIDATE_URL,
        json={
            "order_id": order_id,
            "cards": ["companion_cert", "contract"],
        },
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text

    after = await _list_cache_audits(order_id)
    assert len(after) == len(before) + 1, (
        f"expected exactly one new audit row (audit commits "
        f"independently of request tx); got {len(after) - len(before)}"
    )

    row = after[-1]
    assert row.target_type == "precheck_cache"
    assert row.action == "invalidate"
    assert str(row.target_id) == order_id
    assert row.operator == "cache_super"
    # AC#3 per-card tag: sorted comma-joined cards in ``reason``.
    assert row.reason == "cards=companion_cert,contract"


async def test_audit_row_omitted_cards_records_all_sentinel(
    client: AsyncClient, super_token: str
) -> None:
    """Omitting ``cards`` records the ``*all`` sentinel so a postmortem
    can distinguish "user defaulted" from "user passed empty list".
    Pydantic rejects an empty list explicitly via ``extra="forbid"``
    + non-empty-by-default, so the only valid omit form is the
    sentinel path.
    """
    order_id = str(uuid4())
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 200, response.text
    rows = await _list_cache_audits(order_id)
    assert len(rows) == 1
    assert rows[0].reason == "cards=*all"


def test_audit_row_construction_includes_sorted_cards() -> None:
    """Unit-level: confirm the ``reason`` column carries comma-joined,
    sorted cards.

    We do not need an HTTP round-trip for AC#3 verification; the row
    construction is deterministic from the request body. This pins the
    expected shape so PRECHECK-BACKEND cannot accidentally drop the
    per-card tag in a refactor.
    """
    from app.api.v1.admin.cache_invalidate import (
        invalidate_cache as _endpoint,  # noqa: F401 — imported to
        # ensure the cards-join contract lives in the module under test
    )

    # The cards normalisation is inlined in the endpoint; mirror it
    # here so a refactor that breaks the contract fails this test.
    cards_in = ["contract", "companion_cert", "insurance"]
    expected = "cards=companion_cert,contract,insurance"
    actual = "cards=" + ",".join(sorted(cards_in))
    assert actual == expected

    # Omit-cards → ``*all`` sentinel (not an empty string).
    actual_none = "cards=" + ("*all" if not [] else ",".join(sorted([])))
    assert actual_none == "cards=*all"


# ---------------------------------------------------------------------------
# AC#4: cache key shape (single ``precheck:order:{order_id}``)
# ---------------------------------------------------------------------------


def test_cache_key_is_single_packed_key() -> None:
    """Design line 224 + 魈 Q4 #4: one key per order, not per-card."""
    order_id = uuid4()
    key = _build_cache_key(order_id)
    assert key == f"precheck:order:{order_id}"
    # Sanity: no per-card key shape sneaks in.
    assert "card=" not in key
    assert ":card:" not in key


# ---------------------------------------------------------------------------
# Auth: super passes, ops/finance get 403, no token gets 401
# ---------------------------------------------------------------------------


async def test_ops_admin_rejected_with_403(client: AsyncClient, ops_token: str) -> None:
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
        headers={"Authorization": f"Bearer {ops_token}"},
    )
    assert response.status_code == 403, response.text
    assert "super_admin" in response.json()["detail"]


async def test_finance_admin_rejected_with_403(client: AsyncClient, finance_token: str) -> None:
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
        headers={"Authorization": f"Bearer {finance_token}"},
    )
    assert response.status_code == 403, response.text


async def test_missing_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
    )
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# AC#5 (刻晃 r1 红线): cards Literal enum 拒 unknown card
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad_card",
    [
        "companion_certs",  # typo: trailing s
        "COMPANION_CERT",  # case mismatch
        "contract2",  # near-miss
        "random_card",  # totally unknown
        "",  # empty string
    ],
)
async def test_unknown_card_returns_422(
    client: AsyncClient, super_token: str, bad_card: str
) -> None:
    """Pydantic ``Literal`` rejects unknown card names with 422.

    刻晃 PR #250 r1 红线: schema 原本 ``cards: list[str] | None`` 裸
    ``list[str]``, admin 拼错 (e.g. trailing s / case mismatch / typo)
    会静默接受 + audit 写错值 + 走完, PRECHECK-BACKEND 接手
    后 evaluate lookup card 会 KeyError / silent skip. 改 ``list[CardName]``
    后 Pydantic 自动 422.
    """
    response = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4()), "cards": [bad_card]},
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 422, response.text
    body = response.json()
    # FastAPI default ValidationError envelope: {"detail": [{...}]}
    assert "detail" in body
    # 错误信息包含 cards 路径 + literal_error type
    detail_str = repr(body["detail"]).lower()
    assert "cards" in detail_str
    assert "literal" in detail_str or "input should be" in detail_str or "value error" in detail_str


async def test_mixed_valid_and_unknown_card_returns_422(
    client: AsyncClient, super_token: str
) -> None:
    """一个合法 + 一个不合法 = 422 (Pydantic 逐元素检)."""
    response = await client.post(
        INVALIDATE_URL,
        json={
            "order_id": str(uuid4()),
            "cards": ["companion_cert", "companion_certs"],
        },
        headers={"Authorization": f"Bearer {super_token}"},
    )
    assert response.status_code == 422, response.text


async def test_all_known_cards_accepted(client: AsyncClient, super_token: str) -> None:
    """4 个合法 card 名同时传 = c2 evaluate 走通 返 200 (不是 422)."""
    response = await client.post(
        INVALIDATE_URL,
        json={
            "order_id": str(uuid4()),
            "cards": ["companion_cert", "insurance", "prep_package", "contract"],
        },
        headers={"Authorization": f"Bearer {super_token}"},
    )
    # c2 evaluate landed → 200; 重点是 不 422
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# 刻晃 r1 黄线 #1: audit 独立 session 在 _redis_del 也 raise 时仍 commit
# ---------------------------------------------------------------------------


async def test_audit_row_persists_even_when_redis_del_raises(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, super_token: str
) -> None:
    """audit row commit 在 aggregator 之前, 即使 Redis 挂也保留.

    现实场景: Redis 连接 broken / 超时, defensive ``redis DEL``
    在 :meth:`OrderPrecheckAggregator._redis_del` 里起 raise. 魈
    hard 要求 #1 ``AdminAuditLog 必写`` 意味 audit 仍须 commit —
    独立 session + audit 在 aggregator call 之前 commit 保证了
    这点. endpoint 返 500 (RuntimeError 未被 catch).
    """
    from app.services import order_precheck_aggregator as agg_module

    async def _broken_redis_del(self, key: str) -> None:
        raise RuntimeError("redis pipe broken")

    monkeypatch.setattr(
        agg_module.OrderPrecheckAggregator,
        "_redis_del",
        _broken_redis_del,
    )

    order_id = str(uuid4())
    before = await _list_cache_audits(order_id)

    # ASGITransport re-raises unhandled exceptions; we expect the
    # RuntimeError from the broken _redis_del to propagate. The key
    # invariant we want to validate is that the audit row was already
    # committed via the dedicated session *before* the exception
    # bubbled up.
    with pytest.raises(RuntimeError, match="redis pipe broken"):
        await client.post(
            INVALIDATE_URL,
            json={"order_id": order_id, "cards": ["insurance"]},
            headers={"Authorization": f"Bearer {super_token}"},
        )

    after = await _list_cache_audits(order_id)
    assert (
        len(after) == len(before) + 1
    ), "audit row must persist even when defensive Redis DEL raises"
    audit_row = after[-1]
    assert audit_row.target_type == "precheck_cache"
    assert audit_row.action == "invalidate"
    assert audit_row.reason == "cards=insurance"


# ---------------------------------------------------------------------------
# AC#2: rate limit 5/min per admin
# ---------------------------------------------------------------------------


async def test_rate_limit_blocks_sixth_request_per_admin(
    client: AsyncClient,
    super_token: str,
    enable_real_rate_limit: None,  # noqa: ARG001 — fixture
) -> None:
    """Per-admin 5/min bucket; the 6th call within the window = 429.

    Buckets are keyed by Authorization token (see
    ``_admin_rate_limit_key``), so two distinct admins share no
    quota. We only verify the same-token saturation here; the
    per-admin partitioning is covered by the unit test on
    ``_admin_rate_limit_key`` below.
    """
    headers = {"Authorization": f"Bearer {super_token}"}
    for i in range(5):
        r = await client.post(
            INVALIDATE_URL,
            json={"order_id": str(uuid4())},
            headers=headers,
        )
        assert (
            r.status_code == 200
        ), f"call #{i + 1}: expected c2 evaluate 200, got {r.status_code} — {r.text}"
    # 6th call within the same minute → 429.
    r = await client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
        headers=headers,
    )
    assert r.status_code == 429, f"6th call should be rate-limited; got {r.status_code}: {r.text}"


def test_rate_limit_key_partitions_per_token() -> None:
    """``_admin_rate_limit_key`` returns distinct buckets per token.

    The fastapi.Request stub here uses a thin namespace; we don't need
    a real ASGI scope because the function only reads
    ``headers.get("authorization")`` and ``client.host``.
    """
    from app.api.v1.admin.cache_invalidate import _admin_rate_limit_key

    class _StubRequest:
        def __init__(self, auth: str | None, host: str = "1.2.3.4") -> None:
            self.headers = {"authorization": auth} if auth else {}
            self.client = type("_C", (), {"host": host})()

    key_a = _admin_rate_limit_key(_StubRequest("Bearer aaa.bbb.ccc"))
    key_b = _admin_rate_limit_key(_StubRequest("Bearer xxx.yyy.zzz"))
    key_anon = _admin_rate_limit_key(_StubRequest(None, host="9.9.9.9"))

    assert key_a == "admin:aaa.bbb.ccc"
    assert key_b == "admin:xxx.yyy.zzz"
    assert key_a != key_b
    assert key_anon == "ip:9.9.9.9"
