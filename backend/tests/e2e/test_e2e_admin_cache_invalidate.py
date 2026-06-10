"""E2E: admin cache invalidate endpoint (S3-TEST-005-CACHE-INVALIDATE).

Covers PR #250 (S3-DEV-005-CACHE-INVALIDATE) merged to main @
sha ``7d327c8`` (14:03:15Z, 11/11 unit test PASS) end-to-end. Unit
tests live at ``backend/tests/api/v1/test_admin_cache_invalidate.py``
and focus on isolated assertions; this E2E suite reuses the shared
``client`` + ``fake_redis`` + SQLite harness to verify the full HTTP
stack (real dep injection, real schema validation, real audit
session, real fake_redis store) under the canonical ``/api/v1/admin/
cache/invalidate`` route.

AC coverage (per S3-TEST-005 acceptance criteria):

* AC#1 — super_admin reaches handler; ops / finance / missing-token
  rejected; non-super roles do NOT leave a successful audit row.
* AC#2 — body schema validation (Literal + ``extra=forbid``); invalid
  card name returns 422 and does not DEL the cache.
* AC#3 — defensive Redis DEL targets only the ``precheck:order:
  {order_id}`` key for the requested order; unrelated keys survive.
* AC#4 — real aggregator (S3-DEV-003-PRECHECK-BACKEND c2 merged
  main @ ``c85b170``, 2026-06-10T20:07Z) returns 200 with
  ``invalidated_keys`` + ``broadcast`` (broadcast still False until
  c4 WS infra lands).
* AC#5 — AdminAuditLog is durable on the 200 path; the dedicated
  ``AuditSession`` commits before the aggregator runs so audit
  trace survives even if aggregator raises later (rollback case
  covered in unit test, see ``backend/tests/api/v1/
  test_admin_cache_invalidate.py``).
* AC#6 — rate limit 5/min per admin token; 6th call returns 429; two
  different admin tokens have isolated buckets.
* AC#7 — per-card audit fidelity: explicit ``cards=[...]`` list is
  preserved verbatim (sorted, comma-joined) in
  ``AdminAuditLog.reason``.
* AC#8 — endpoint is reachable via the documented OpenAPI path
  (smoke; full OpenAPI schema check is a CI gate, not duplicated
  here).
* **AC#10 — cards=[] empty list design intent** (PR #250 r2 design
  intent ack by hutao): empty list ≡ omit ``cards`` ≡ ``"*all"``
  sentinel. Schema does NOT carry ``Field(min_length=1)`` — that is
  intentional, not an oversight. Verified by 200 on cards=[] path
  reaching the real aggregator (not 422 from Pydantic). If E2E ever
  flips this assumption (admin clients accidentally posting
  ``cards=[]`` and corrupting audit semantics), open a bug task to
  add ``min_length=1`` and return 422; do **not** silently change
  the test.

AC#9 (CI gate) is verified by GitHub Actions, not by this file.

All tests share the same ``e2e_client`` + ``fake_redis`` fixtures from
``backend/tests/e2e/conftest.py`` and ``backend/tests/conftest.py``.
Each test seeds its own AdminUser to avoid rate-limit bucket pollution
and uses a fresh ``uuid4()`` order id so cache keys do not collide.
"""
from __future__ import annotations

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

pytestmark = pytest.mark.e2e

INVALIDATE_URL = "/api/v1/admin/cache/invalidate"


# ---------------------------------------------------------------------------
# Fixtures (admin seed + rate-limit enable helpers).
# These intentionally mirror the unit-test fixtures in
# ``tests/api/v1/test_admin_cache_invalidate.py`` so behavior is
# equivalent under the e2e harness; we keep them local instead of
# pulling them into ``e2e/conftest.py`` to avoid leaking admin-only
# auth machinery into unrelated e2e suites.
# ---------------------------------------------------------------------------


async def _seed_admin_token(username: str, role: AdminRole) -> str:
    """Seed an ``AdminUser`` with the requested role and return its JWT.

    The unique-username constraint forces every test to pass a
    distinct ``username`` (we suffix with ``uuid4().hex[:6]`` from the
    caller). Returns a fresh ``Authorization: Bearer <token>`` value
    ready to drop into request headers.
    """
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
async def super_token_e2e() -> str:
    """Fresh ``super_`` admin token, unique per test."""
    return await _seed_admin_token(f"e2e_super_{uuid4().hex[:6]}", AdminRole.super_)


@pytest.fixture
async def ops_token_e2e() -> str:
    """Fresh ``ops`` admin token (used for 403 negative tests)."""
    return await _seed_admin_token(f"e2e_ops_{uuid4().hex[:6]}", AdminRole.ops)


@pytest.fixture
async def finance_token_e2e() -> str:
    """Fresh ``finance`` admin token (used for 403 negative tests)."""
    return await _seed_admin_token(
        f"e2e_finance_{uuid4().hex[:6]}", AdminRole.finance
    )


@pytest.fixture
def enable_real_rate_limit_e2e() -> AsyncGenerator[None, None]:
    """Override the e2e ``_disable_slowapi_limiter`` autouse.

    e2e's ``conftest._disable_slowapi_limiter`` turns the limiter off
    by default so OTP send-rate doesn't pollute unrelated e2e tests.
    AC#6 needs a real bucket; we re-enable and reset the slowapi store
    afterwards so other tests don't inherit our spent quota.
    """
    prev = _rate_limiter.enabled
    _rate_limiter.enabled = True
    try:
        yield
    finally:
        _rate_limiter.enabled = prev
        _rate_limiter.reset()


async def _list_cache_audits(order_id: str) -> list[AdminAuditLog]:
    """Read audit rows for a given order_id directly from SQLite.

    Reads via ``_session_factory()`` (fresh session) so we bypass any
    request-scoped session cache. Filters to
    ``target_type='precheck_cache'`` + ``action='invalidate'`` so
    audits from unrelated tests on the same in-memory DB do not bleed
    in.
    """
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


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# AC#1 — ABAC matrix (super passes; ops / finance / missing token rejected).
# ---------------------------------------------------------------------------


async def test_e2e_super_admin_reaches_handler(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#1 happy path: super_admin reaches the handler.

    Real aggregator landed (S3-DEV-003-PRECHECK-BACKEND c2 merged main
    @ sha ``c85b170``); endpoint now returns 200 with
    ``invalidated_keys`` + ``broadcast``. Assertion is the response is
    200 (not 401/403/422) which proves every pre-handler gate (auth +
    ABAC + schema) is cleared and the aggregator path returned a
    real summary.
    """
    order_id = str(uuid4())
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert f"precheck:order:{order_id}" in body["invalidated_keys"], (
        f"invalidated_keys must include precheck:order:{order_id}; got {body}"
    )
    assert isinstance(body["broadcast"], bool), (
        f"broadcast field must be bool (c4 WS infra still stub False); got {body}"
    )
    audits = await _list_cache_audits(order_id)
    assert len(audits) == 1, (
        "super_admin reaching handler must persist exactly one audit row"
    )


async def test_e2e_ops_role_returns_403_no_success_audit(
    e2e_client: AsyncClient, ops_token_e2e: str
) -> None:
    """AC#1: ``ops`` is rejected by ``get_super_admin`` with 403.

    Also verifies the dependency raises *before* the handler runs, so
    no audit row is persisted (the audit add+commit lives inside the
    handler body).
    """
    order_id = str(uuid4())
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers=_auth(ops_token_e2e),
    )
    assert response.status_code == 403, response.text
    audits = await _list_cache_audits(order_id)
    assert audits == [], "non-super role must not produce an audit row"


async def test_e2e_finance_role_returns_403_no_success_audit(
    e2e_client: AsyncClient, finance_token_e2e: str
) -> None:
    """AC#1: ``finance`` is rejected by ``get_super_admin`` with 403."""
    order_id = str(uuid4())
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers=_auth(finance_token_e2e),
    )
    assert response.status_code == 403, response.text
    audits = await _list_cache_audits(order_id)
    assert audits == []


async def test_e2e_missing_token_returns_401_or_422(
    e2e_client: AsyncClient,
) -> None:
    """AC#1: missing ``Authorization`` returns 401 (decoded admin dep)
    or 422 (FastAPI required-header validation). Either is acceptable
    as long as the response is *not* 501 (which would mean the handler
    ran without auth).
    """
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
    )
    assert response.status_code in (401, 422), response.text


async def test_e2e_wrong_token_returns_401(
    e2e_client: AsyncClient,
) -> None:
    """AC#1: garbage bearer token returns 401 (admin JWT decode fails)."""
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
        headers=_auth("garbage.not.a.jwt"),
    )
    assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# AC#2 — body schema validation (Literal card names + extra=forbid).
# ---------------------------------------------------------------------------


async def test_e2e_invalid_card_name_returns_422_no_del(
    e2e_client: AsyncClient, super_token_e2e: str, fake_redis: Any
) -> None:
    """AC#2: typo card name (e.g. plural form) hits Pydantic Literal
    and returns 422. Seeds a cache key first and asserts it survives
    (no DEL because the request never reached the handler).
    """
    order_id = uuid4()
    key = _build_cache_key(order_id)
    await fake_redis.set(key, '{"untouched": true}')

    response = await e2e_client.post(
        INVALIDATE_URL,
        json={
            "order_id": str(order_id),
            "cards": ["companion_certs"],  # plural typo — Literal rejects
        },
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 422, response.text
    assert await fake_redis.get(key) is not None, (
        "422 (Pydantic validation) must not run the handler -> no DEL"
    )
    assert await _list_cache_audits(str(order_id)) == [], (
        "422 (Pydantic validation) must not write an audit row"
    )


async def test_e2e_unknown_body_field_returns_422(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#2: ``extra=forbid`` on the request schema rejects unknown
    fields (e.g. a misnamed ``order_ids``)."""
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={
            "order_id": str(uuid4()),
            "order_ids": ["bonus-field"],  # should be rejected
        },
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 422, response.text


async def test_e2e_missing_order_id_returns_422(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#2: ``order_id`` is required by the schema."""
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# AC#3 — defensive Redis DEL hits only the order key.
# ---------------------------------------------------------------------------


async def test_e2e_defensive_del_targets_only_order_key(
    e2e_client: AsyncClient, super_token_e2e: str, fake_redis: Any
) -> None:
    """AC#3: invalidate order A only deletes ``precheck:order:{A}``;
    unrelated keys (other order, other namespace) survive."""
    order_a = uuid4()
    order_b = uuid4()
    key_a = _build_cache_key(order_a)
    key_b = _build_cache_key(order_b)
    other_key = "some:unrelated:namespace:42"

    await fake_redis.set(key_a, '{"order_a": true}')
    await fake_redis.set(key_b, '{"order_b": true}')
    await fake_redis.set(other_key, "untouched")

    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_a)},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text

    # AC#3: only the target order key is deleted. The aggregator
    # subsequently re-SETs the recomputed value with TTL 5min, so the
    # post-call ``GET`` returns the newly-computed payload, not None.
    # The defensive contract is unchanged: unrelated keys survive.
    assert await fake_redis.get(key_b) is not None, "other order's key must survive"
    assert await fake_redis.get(other_key) is not None, (
        "unrelated namespace key must survive"
    )


# ---------------------------------------------------------------------------
# AC#4 — real aggregator landed (S3-DEV-003-PRECHECK-BACKEND c2 merged
# main @ sha ``c85b170`` 2026-06-10T20:07Z). Endpoint returns 200 with
# ``invalidated_keys`` + ``broadcast``; broadcast remains False until
# c4 WS infra lands.
#
# CANARY HISTORY: the prior version of this test asserted 501 with a
# ``S3-DEV-003-PRECHECK-BACKEND`` marker as a canary for the stub
# window. The 501→200 flip is the intended canary trigger; we update
# the test (NOT revert the endpoint) per the canary block in this
# module's docstring.
# ---------------------------------------------------------------------------


async def test_e2e_real_aggregator_returns_200_with_summary(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#4 post-canary: real aggregator returns 200 with a summary.

    Verifies the 200 response shape:
    * ``invalidated_keys`` lists the ``precheck:order:{order_id}`` key
      that was DEL'd (single key per ADR-0048 §6 + 魈 Q4 #4 — one
      packed key per order, not per-card).
    * ``broadcast`` is bool (currently False per c2 stub; flips True
      once c4 WS infra lands — that flip is a follow-up canary on a
      separate test, not this one).
    """
    order_id = str(uuid4())
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": order_id},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["invalidated_keys"] == [f"precheck:order:{order_id}"], (
        f"invalidated_keys must be exactly the single packed key; got {body}"
    )
    assert isinstance(body["broadcast"], bool), (
        f"broadcast must be bool (c4 stub False); got {body}"
    )


# ---------------------------------------------------------------------------
# AC#5 — audit row written before aggregator runs (dedicated
# AuditSession). 200 path verifies the audit trace is durable in the
# happy case; an explicit aggregator-failure case would need DI
# override (out of scope for this E2E suite — covered in unit test).
# ---------------------------------------------------------------------------


async def test_e2e_audit_row_persists_on_200_path(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#5: the audit row is committed via a dedicated session before
    the aggregator runs. On the 200 happy path we assert the row
    exists by querying via a *fresh* session (no shared transaction
    view), proving the dedicated-session pattern works.

    Rollback durability (audit row survives even if aggregator raises
    after audit commit) is covered by the unit test
    ``backend/tests/api/v1/test_admin_cache_invalidate.py``; E2E does
    not synthesize aggregator failures because the real aggregator
    needs DI override at fixture level.
    """
    order_id = uuid4()
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_id), "cards": ["insurance"]},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text

    audits = await _list_cache_audits(str(order_id))
    assert len(audits) == 1, "200 path must produce exactly one audit row"
    row = audits[0]
    assert row.action == "invalidate"
    assert row.target_type == "precheck_cache"
    assert str(row.target_id) == str(order_id)


async def test_e2e_audit_row_has_operator_and_target_fields(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#5: operator (username) and target_id (order UUID) are
    populated so post-incident audit reconstruction is possible."""
    order_id = uuid4()
    await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_id)},
        headers=_auth(super_token_e2e),
    )

    audits = await _list_cache_audits(str(order_id))
    assert len(audits) == 1
    row = audits[0]
    assert row.operator and row.operator.startswith("e2e_super_"), (
        f"operator must carry the admin's username, got {row.operator!r}"
    )
    assert row.reason == "cards=*all", (
        "omitted ``cards`` must record the ``*all`` sentinel"
    )


# ---------------------------------------------------------------------------
# AC#6 — rate limit 5/min per admin token; 6th returns 429; isolation.
# ---------------------------------------------------------------------------


async def test_e2e_rate_limit_6th_call_returns_429(
    e2e_client: AsyncClient,
    super_token_e2e: str,
    enable_real_rate_limit_e2e: None,
) -> None:
    """AC#6: 5 calls in the same window pass (200 real aggregator);
    the 6th returns 429."""
    order_id = str(uuid4())
    payload = {"order_id": order_id}
    headers = _auth(super_token_e2e)

    for i in range(5):
        r = await e2e_client.post(INVALIDATE_URL, json=payload, headers=headers)
        assert r.status_code == 200, (
            f"call #{i + 1} expected 200 (real aggregator), got {r.status_code} {r.text}"
        )

    r = await e2e_client.post(INVALIDATE_URL, json=payload, headers=headers)
    assert r.status_code == 429, (
        f"call #6 must be rate-limited, got {r.status_code} {r.text}"
    )


async def test_e2e_rate_limit_per_admin_token_isolated(
    e2e_client: AsyncClient,
    enable_real_rate_limit_e2e: None,
) -> None:
    """AC#6 isolation: two different admin tokens have independent
    buckets. After admin A burns 5/5, admin B must still get 200
    (handler ran), not 429."""
    super_a = await _seed_admin_token(
        f"e2e_super_a_{uuid4().hex[:6]}", AdminRole.super_
    )
    super_b = await _seed_admin_token(
        f"e2e_super_b_{uuid4().hex[:6]}", AdminRole.super_
    )
    payload = {"order_id": str(uuid4())}

    for i in range(5):
        r = await e2e_client.post(
            INVALIDATE_URL, json=payload, headers=_auth(super_a)
        )
        assert r.status_code == 200, f"admin A call {i + 1}: {r.status_code}"

    # admin A is now spent.
    r_a6 = await e2e_client.post(
        INVALIDATE_URL, json=payload, headers=_auth(super_a)
    )
    assert r_a6.status_code == 429, "admin A 6th call must 429"

    # admin B has an independent bucket.
    r_b1 = await e2e_client.post(
        INVALIDATE_URL, json=payload, headers=_auth(super_b)
    )
    assert r_b1.status_code == 200, (
        f"admin B 1st call must be handled (200 real aggregator), got {r_b1.status_code}"
    )


# ---------------------------------------------------------------------------
# AC#7 — per-card audit fidelity (verbatim cards list).
# ---------------------------------------------------------------------------


async def test_e2e_per_card_audit_records_full_cards_list(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#7: an explicit cards list with multiple cards is preserved
    verbatim (sorted, comma-joined) in ``AdminAuditLog.reason`` so
    per-card remediation drives can be reconstructed."""
    order_id = uuid4()
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={
            "order_id": str(order_id),
            "cards": ["prep_package", "companion_cert", "insurance"],
        },
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text

    audits = await _list_cache_audits(str(order_id))
    assert len(audits) == 1
    # sorted alphabetically: companion_cert, insurance, prep_package
    assert audits[0].reason == "cards=companion_cert,insurance,prep_package", (
        f"per-card audit reason mismatch: {audits[0].reason!r}"
    )


# ---------------------------------------------------------------------------
# AC#8 — endpoint reachable via documented OpenAPI path (smoke).
# Full OpenAPI schema validation is a CI gate (``openapi.json`` diff +
# ``docs/api/admin-cache.md`` regenerate). We only smoke that the
# canonical path is mounted under the documented prefix.
# ---------------------------------------------------------------------------


async def test_e2e_endpoint_reachable_via_openapi_path(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#8 smoke: ``/api/v1/admin/cache/invalidate`` is reachable
    (not 404). 200 from the real aggregator proves the route is
    mounted and the handler ran end-to-end."""
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(uuid4())},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code != 404, "endpoint must be mounted"
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# AC#10 — cards=[] empty list design intent.
#
# PR #250 r2 review (hutao msg #2 @ 13:51 UTC) explicitly declares:
#   * ``cards=[]`` ≡ ``cards=None`` ≡ ``"*all"`` sentinel.
#   * 3 reasons: endpoint contract (``cards is None or len(cards)==0``
#     both go to the ``"*all"`` audit sentinel + invalidate the whole
#     packed key); client-friendly (front-end can post ``cards=[]``
#     equivalent to omitting); schema's lack of ``Field(min_length=1)``
#     is intentional, not an oversight.
#
# **Reverse case ack**: if any of the three tests below fail (e.g.
# Pydantic does reject empty list, or audit records something other
# than ``*all`` for empty list, or the response is not 501), the
# design intent is contradicted -- file
# ``S3-BUG-005-CACHE-CARDS-EMPTY-LIST-DESIGN-INTENT`` (P1, related_to
# this task) so hutao + 魈 can decide whether to:
#   (a) add ``Field(min_length=1)`` and flip the contract to 422, or
#   (b) fix the handler to honor empty list ≡ omit.
# Do NOT silently mutate the tests to fit the observed behavior.
# ---------------------------------------------------------------------------


async def test_e2e_empty_cards_list_equivalent_to_omit_sentinel(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#10 (a): ``cards=[]`` (empty list) must NOT be rejected by
    Pydantic schema validation; the request reaches the handler.

    Verified by asserting the response is 200 (real aggregator
    handler reached), not 422 (Pydantic rejected at validation).
    """
    order_id = str(uuid4())
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": order_id, "cards": []},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, (
        f"empty cards list must NOT trigger 422; got {response.status_code} "
        f"-- design intent contradicted, open S3-BUG-005-CACHE-CARDS-EMPTY-"
        f"LIST-DESIGN-INTENT. Body: {response.text}"
    )


async def test_e2e_empty_cards_audit_records_all_sentinel(
    e2e_client: AsyncClient, super_token_e2e: str
) -> None:
    """AC#10 (b): an empty-list ``cards=[]`` must record the same
    ``"*all"`` sentinel in ``AdminAuditLog.reason`` that omitting
    ``cards`` produces -- the two paths are semantically equivalent.

    This is the strongest design-intent check: if the handler treats
    ``[]`` and ``None`` differently (e.g. records ``"cards="`` empty
    string), the audit trail diverges and the ``*all`` sentinel
    semantics break. File a P1 bug if this fails.
    """
    order_id = uuid4()
    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_id), "cards": []},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text

    audits = await _list_cache_audits(str(order_id))
    assert len(audits) == 1, (
        "empty cards list must still produce exactly one audit row "
        "(it is a valid handler call)"
    )
    assert audits[0].reason == "cards=*all", (
        f"empty list MUST record the *all sentinel (≡ omit cards). "
        f"Got reason={audits[0].reason!r}. If this fails, design intent "
        f"is contradicted -- file S3-BUG-005-CACHE-CARDS-EMPTY-LIST-"
        f"DESIGN-INTENT (P1, related_to S3-TEST-005)."
    )


async def test_e2e_empty_cards_returns_200_like_omit(
    e2e_client: AsyncClient, super_token_e2e: str, fake_redis: Any
) -> None:
    """AC#10 (c): ``cards=[]`` reaches the aggregator path and returns
    200 (real aggregator) identically to omitting ``cards``. Also
    confirms the defensive DEL fires for the empty-list case (same
    code path as omit) — note the aggregator re-SETs the recomputed
    value, so the assertion is on the response body shape, not on the
    post-call ``GET`` returning None.
    """
    order_id = uuid4()
    key = _build_cache_key(order_id)
    await fake_redis.set(key, '{"stale": true}')

    response = await e2e_client.post(
        INVALIDATE_URL,
        json={"order_id": str(order_id), "cards": []},
        headers=_auth(super_token_e2e),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert key in body["invalidated_keys"], (
        f"defensive DEL must run for cards=[] (same orchestrator path "
        f"as omit) — invalidated_keys must list {key}; got {body}. "
        f"If it doesn't, the empty-list branch diverged from the omit "
        f"branch -- file S3-BUG-005."
    )
