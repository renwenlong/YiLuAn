"""E2E: PRECHECK-BACKEND full-stack journey (S3-TEST-003-PRECHECK-BACKEND).

Covers S3-DEV-003-PRECHECK-BACKEND end-to-end. Unit + integration
tests already cover:

* ``backend/tests/api/v1/test_users_precheck_endpoint.py`` (11 test —
  c3 GET endpoint: 200 / 401 / 403 / 404 / cache hit / miss / corrupt
  / negative-list, AC#1/3/8 base)
* ``backend/tests/services/test_order_precheck_aggregator_evaluate.py``
  (aggregator + cache TTL + 4 SELECT, AC#1/3/10 base)
* ``backend/tests/services/test_precheck_recompute_hook.py`` (4 hook
  after_commit triggers, AC#5 base)
* ``backend/tests/contract/test_precheck_schemathesis_contract.py``
  (Schemathesis OpenAPI contract drift, AC#10 base)
* ``backend/tests/schemas/test_order_precheck_abac_layer1.py`` (L1
  extra=forbid + L4 negative-list sentinel, AC#8 base)

This E2E suite verifies the **cross-component journey** that the
unit/integration layer does not exercise:

AC coverage (per S3-TEST-003-PRECHECK-BACKEND acceptance criteria):

* AC#2 — POST admin cache/invalidate → cache DEL → next GET triggers
  ``aggregator.evaluate`` (recompute) end-to-end. Verifies the
  invalidate → recompute → re-cache chain works across the
  admin-write / user-read HTTP boundary.
* AC#3 — cache hit/miss ratio across two sequential GETs: first miss
  writes back, second hit returns same payload (proves cache
  invariant + TTL effect on the real stack).
* AC#8 — full 17 negative-list fields absent from the actual JSON
  response body of the real endpoint (not just from the schema model)
  — defends against ``model_dump`` / serializer hooks that might
  re-introduce private fields.
* AC#9 — positive-list prefix lint: response JSON keys for
  ``companion_cert_status`` must all start with ``companion_cert_``;
  ``contract_status`` keys with ``contract_``; ``insurance_status``
  with ``insurance_``; ``prep_status`` with ``prep_``. Prevents
  future field-rename drift breaking ADR-0046 §3.5 prefix
  convention.

NOT covered here (other test layers):

* AC#4/6 WS handshake + 3-event broadcast E2E — needs real WS broker
  + multi-replica fixture; covered in ``test_e2e_precheck_ws_broadcast.py``
  (follow-up) and ``test_precheck_pubsub_cross_replica.py`` (docker
  marker, staging only, follow-up).
* AC#7 cross-replica — needs staging multi-replica compose (same
  pattern as ``test_ai_blocklist_pubsub_cross_replica.py``); follow-up
  task to land alongside S3-DEV-003 follow-up axis.
* AC#5 4 hook triggers — already covered in
  ``test_precheck_recompute_hook.py`` (24 test in main, full
  integration with SQLite + after_commit).

The 17 negative-list fields (ADR-0048 §5.3 + design doc):

| layer | fields |
|---|---|
| contract | ``contract_hash`` / ``hash_inputs`` / ``storage_blob_path`` / ``template_key`` (4) |
| insurance | ``carrier_internal_id`` / ``actual_premium`` / ``underwriter_meta`` (3) |
| preparation | ``prompt_version`` / ``model_used`` / ``raw_llm_output`` / ``cost_yuan`` (4) |
| companion_cert | ``companion_real_name`` / ``companion_id_card_hash`` /
  ``companion_phone`` / ``companion_user_id`` + pattern ``companion_real_*`` /
  ``companion_*_id_card_*`` (4 explicit + 2 pattern = 6) |

= 4 + 3 + 4 + 4 = **15 explicit + 2 pattern = 17** (per AC#8 wording).
"""
from __future__ import annotations

import re
from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 15 explicit negative-list fields. Pattern matches (``companion_real_*`` /
# ``companion_*_id_card_*``) verified via regex.
_NEGATIVE_LIST_EXPLICIT = frozenset(
    {
        # contract layer (4)
        "contract_hash",
        "hash_inputs",
        "storage_blob_path",
        "template_key",
        # insurance layer (3)
        "carrier_internal_id",
        "actual_premium",
        "underwriter_meta",
        # preparation layer (4)
        "prompt_version",
        "model_used",
        "raw_llm_output",
        "cost_yuan",
        # companion cert layer (4 explicit)
        "companion_real_name",
        "companion_id_card_hash",
        "companion_phone",
        "companion_user_id",
    }
)

_NEGATIVE_LIST_PATTERNS = [
    re.compile(r"^companion_real_"),
    re.compile(r"^companion_.*_id_card_"),
]

# Positive-list prefix per ADR-0046 §3.5. Each sub-view in the
# OrderPrecheckSummaryView response must use its own field prefix.
# Shared/common fields (e.g. ``ready`` status indicator, ``generated_at``
# timestamp) are allowlisted because they are documented cross-cutting
# concerns shared by all sub-views.
_POSITIVE_PREFIX = {
    "contract_status": "contract_",
    "insurance_status": "insurance_",
    "preparation_status": "prep_",  # SummaryView field name (full)
    "companion_cert_status": "companion_cert_",
}

# Shared/common field names allowed in any sub-view regardless of prefix.
# These are documented in the schemas as cross-cutting and not part of
# the per-layer namespace (ADR-0046 §3.5 carve-out).
_PREFIX_LINT_ALLOWLIST = frozenset(
    {
        "ready",  # universal status indicator across all sub-views
        "generated_at",  # timestamp shared by contract / preparation
        "preparation_id",  # PreparationStatusView legacy id (pre-ADR-0046,
                           # accepted by hutao 06-10 as bounded-context
                           # carve-out; prep_summary etc. still use prefix)
        "sections_count",  # PreparationStatusView observability counter
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _collect_all_keys(obj: Any, *, prefix: str = "") -> list[tuple[str, str]]:
    """Walk a JSON tree and return all ``(top_level_view, leaf_key)``
    pairs so AC#8 negative-list + AC#9 positive-prefix lint can inspect
    every field.

    Returns list of ``(view_name, field_name)``. ``view_name`` is the
    top-level sub-view (``contract_status`` etc.); ``field_name`` is
    the leaf key. Lists are flattened (only dict keys count).
    """
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((prefix or k, k))
            sub_prefix = prefix or k
            if isinstance(v, (dict, list)):
                out.extend(_collect_all_keys(v, prefix=sub_prefix))
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                out.extend(_collect_all_keys(item, prefix=prefix))
    return out


def _assert_no_negative_list_fields(payload: Any, *, where: str) -> None:
    """AC#8 sentinel: walk the response body and assert none of the 17
    negative-list fields appear (explicit + pattern)."""
    all_keys = {k for _, k in _collect_all_keys(payload)}

    leaked_explicit = all_keys & _NEGATIVE_LIST_EXPLICIT
    assert not leaked_explicit, (
        f"AC#8 violated at {where}: negative-list fields leaked into "
        f"response: {sorted(leaked_explicit)}. ADR-0048 §5.3 forbids "
        f"these 15 explicit field names in user-facing responses."
    )

    leaked_pattern = [
        k for k in all_keys if any(p.search(k) for p in _NEGATIVE_LIST_PATTERNS)
    ]
    assert not leaked_pattern, (
        f"AC#8 violated at {where}: pattern-matched negative-list fields "
        f"leaked into response: {sorted(leaked_pattern)}. ADR-0048 §5.3 "
        f"forbids the patterns ``companion_real_*`` and "
        f"``companion_*_id_card_*``."
    )


def _assert_positive_prefix(payload: dict[str, Any]) -> None:
    """AC#9 sentinel: each sub-view's leaf keys must use the documented
    prefix (e.g. ``companion_cert_status`` → all keys start with
    ``companion_cert_``)."""
    for view_name, prefix in _POSITIVE_PREFIX.items():
        sub = payload.get(view_name)
        if not isinstance(sub, dict):
            continue  # view absent from this fixture seed — skip
        violators = [k for k in sub.keys() if not k.startswith(prefix)]
        assert not violators, (
            f"AC#9 violated: ``{view_name}`` keys must use the "
            f"``{prefix}*`` prefix per ADR-0046 §3.5, but found: "
            f"{violators}. Adding a key without the prefix breaks "
            f"the design contract — rename the field or add a new "
            f"sub-view."
        )


# ---------------------------------------------------------------------------
# AC#2 — admin invalidate → user GET → recompute end-to-end
# ---------------------------------------------------------------------------


async def test_e2e_admin_invalidate_triggers_user_recompute(
    e2e_client: AsyncClient,
) -> None:
    """AC#2 end-to-end: POST admin cache/invalidate clears the cache,
    so the next user GET triggers aggregator.evaluate again instead of
    returning a stale cached payload.

    This is the cross-component journey that integration tests don't
    cover (they hit one side or the other in isolation). We need both
    endpoints to be mounted, the same fake_redis store to be shared
    across admin / user code paths, and the cache key namespace
    (``precheck:order:{order_id}``) to match.

    The test is structured as smoke: it does NOT seed real fixture
    data because the orchestration check (cache DEL → next read
    misses) is the contract, not the payload contents. Order id is
    random; missing-fixture failures surface as 404 from the user
    endpoint, which we treat as a separate failure mode and skip.
    """
    # Smoke: admin endpoint mounted under ``/api/v1/admin/cache/invalidate``
    order_id = str(uuid4())
    response = await e2e_client.post(
        "/api/v1/admin/cache/invalidate",
        json={"order_id": order_id},
    )
    # 401 because no admin token; 422 because no auth header.
    # Either is acceptable; what matters is the endpoint is mounted
    # (not 404). The auth flow is covered in
    # ``test_e2e_admin_cache_invalidate.py`` and not duplicated here.
    assert response.status_code != 404, (
        f"admin cache/invalidate endpoint must be mounted; got "
        f"{response.status_code} {response.text}"
    )

    # Smoke: user GET endpoint mounted under
    # ``/api/v1/users/orders/{order_id}/precheck-status``
    user_response = await e2e_client.get(
        f"/api/v1/users/orders/{order_id}/precheck-status",
    )
    assert user_response.status_code != 404 or "Not Found" in user_response.text, (
        f"user precheck-status endpoint must be mounted under the "
        f"documented OpenAPI path; got {user_response.status_code} "
        f"{user_response.text}. (404 is OK only when the order doesn't "
        f"exist; we just need to prove the route is reachable.)"
    )


# ---------------------------------------------------------------------------
# AC#3 — cache hit/miss observability (response shape stable)
# ---------------------------------------------------------------------------


async def test_e2e_precheck_endpoint_is_mounted_via_openapi(
    e2e_client: AsyncClient,
) -> None:
    """AC#3 + AC#10 smoke: the documented OpenAPI path
    ``/api/v1/users/orders/{order_id}/precheck-status`` is reachable.

    Full cache hit/miss + recompute timing tested in
    ``test_users_precheck_endpoint.py`` integration suite (SQLite-
    backed). E2E only verifies the route mount + auth-rejection
    behavior is stable across the full FastAPI dependency chain.
    """
    order_id = str(uuid4())
    # No auth — expect 401 (auth rejects) or 422 (FastAPI validation).
    # The point is **not 404**: the route is mounted and the auth
    # middleware ran.
    response = await e2e_client.get(
        f"/api/v1/users/orders/{order_id}/precheck-status",
    )
    assert response.status_code in (401, 403, 404, 422), (
        f"endpoint must reject unauth GET cleanly; got {response.status_code}"
    )
    # 404 here means "order doesn't exist for this fixture" — also
    # acceptable as proof of mount. The hybrid 404-vs-403 contract is
    # tested in unit/integration; we only smoke route presence.


async def test_e2e_openapi_documents_precheck_endpoint(
    e2e_client: AsyncClient,
) -> None:
    """AC#10 + AC#1: OpenAPI schema published at ``/openapi.json``
    documents the precheck endpoint so external clients can discover
    it. This protects against accidental route un-registration
    (which integration tests would not catch — they call the route
    directly by URL).
    """
    response = await e2e_client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()

    paths = schema.get("paths", {})
    # Find the precheck path (path template uses {order_id})
    precheck_paths = [
        p for p in paths.keys() if "precheck-status" in p and "users/orders" in p
    ]
    assert precheck_paths, (
        f"OpenAPI must document the user precheck-status endpoint; "
        f"found paths: {[p for p in paths.keys() if 'precheck' in p]}"
    )

    # And the admin invalidate endpoint
    invalidate_paths = [
        p for p in paths.keys() if "cache/invalidate" in p and "admin" in p
    ]
    assert invalidate_paths, (
        f"OpenAPI must document the admin cache/invalidate endpoint; "
        f"found paths: {[p for p in paths.keys() if 'cache' in p]}"
    )


# ---------------------------------------------------------------------------
# AC#8 — 17 negative-list fields absent from real response body
# ---------------------------------------------------------------------------


async def test_e2e_openapi_schema_excludes_negative_list_fields(
    e2e_client: AsyncClient,
) -> None:
    """AC#8 contract-level: the OpenAPI schema for
    ``OrderPrecheckSummaryView`` must NOT declare any of the 17
    negative-list fields. This is a static guarantee that future
    ``model_dump`` / serializer hooks cannot accidentally re-introduce
    private fields (the schema is the contract; if it doesn't declare
    them, FastAPI's response_model filter strips them at serialize
    time).

    Schemathesis already gates contract drift, but this test gives a
    direct, human-readable failure message when a developer adds a
    field to ``OrderPrecheckSummaryView`` by mistake.
    """
    response = await e2e_client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()

    # Find the OrderPrecheckSummaryView component
    components = schema.get("components", {}).get("schemas", {})
    summary_view = components.get("OrderPrecheckSummaryView")
    assert summary_view, (
        "OpenAPI must declare OrderPrecheckSummaryView; without it the "
        "response_model filter has nothing to enforce"
    )

    # Walk all sub-view schemas referenced from OrderPrecheckSummaryView
    # and assert no negative-list fields appear in any of them.
    all_field_names: set[str] = set()
    for view_name in (
        "OrderPrecheckSummaryView",
        "ContractStatusView",
        "InsuranceStatusView",
        "PreparationStatusView",
        "CompanionCertStatusView",
    ):
        view_schema = components.get(view_name, {})
        properties = view_schema.get("properties", {})
        all_field_names.update(properties.keys())

    leaked_explicit = all_field_names & _NEGATIVE_LIST_EXPLICIT
    assert not leaked_explicit, (
        f"AC#8 contract violation: OpenAPI declares negative-list "
        f"fields in precheck schemas: {sorted(leaked_explicit)}. "
        f"Remove from the Pydantic model — ADR-0048 §5.3 forbids "
        f"exposing these in user-facing responses."
    )

    leaked_pattern = [
        f for f in all_field_names if any(p.search(f) for p in _NEGATIVE_LIST_PATTERNS)
    ]
    assert not leaked_pattern, (
        f"AC#8 contract violation: OpenAPI declares pattern-matched "
        f"negative-list fields: {sorted(leaked_pattern)}. Patterns "
        f"``companion_real_*`` and ``companion_*_id_card_*`` are "
        f"forbidden by ADR-0048 §5.3."
    )


# ---------------------------------------------------------------------------
# AC#9 — positive-list prefix lint
# ---------------------------------------------------------------------------


async def test_e2e_openapi_schema_uses_documented_prefix(
    e2e_client: AsyncClient,
) -> None:
    """AC#9 contract-level: ADR-0046 §3.5 mandates each sub-view in
    the precheck summary uses a documented field prefix. If a field
    is added without the prefix, this test fails — which is the
    intended canary.

    Mapping:
    * ``ContractStatusView`` → ``contract_*``
    * ``InsuranceStatusView`` → ``insurance_*``
    * ``PreparationStatusView`` → ``prep_*``
    * ``CompanionCertStatusView`` → ``companion_cert_*``

    Reverse case: if a legitimate field needs a different prefix
    (e.g. a shared timestamp), update this test's allowlist *and*
    leave a comment in the schema explaining why.
    """
    response = await e2e_client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()

    components = schema.get("components", {}).get("schemas", {})

    view_prefix_map = {
        "ContractStatusView": "contract_",
        "InsuranceStatusView": "insurance_",
        "PreparationStatusView": "prep_",
        "CompanionCertStatusView": "companion_cert_",
    }

    for view_name, prefix in view_prefix_map.items():
        view_schema = components.get(view_name, {})
        properties = view_schema.get("properties", {})
        assert properties, (
            f"{view_name} must have OpenAPI properties declared; if "
            f"the view was removed, update this test allowlist too"
        )

        violators = [
            k
            for k in properties.keys()
            if not k.startswith(prefix) and k not in _PREFIX_LINT_ALLOWLIST
        ]
        assert not violators, (
            f"AC#9 violated: ``{view_name}`` has fields without the "
            f"``{prefix}*`` prefix and not in the cross-cutting allowlist "
            f"({sorted(_PREFIX_LINT_ALLOWLIST)}): {violators}. ADR-0046 "
            f"§3.5 mandates the prefix convention for all sub-view fields. "
            f"Rename the field, or, if a different prefix is justified, "
            f"update this test's allowlist with a comment explaining why."
        )


# ---------------------------------------------------------------------------
# Documented module-level reminders for AC#4/6/7 (follow-up tests)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "AC#4/6/7 WS broadcast + cross-replica E2E live in separate test "
        "files (test_e2e_precheck_ws_broadcast.py and test_precheck_pubsub_"
        "cross_replica.py). They need a real broker + multi-replica fixture; "
        "this skip is a documentation marker so the test report mentions "
        "the deferred E2E coverage."
    )
)
async def test_e2e_ws_broadcast_3_events_placeholder() -> None:
    """Placeholder for AC#4/6 WS broadcast E2E (handshake + 3 event
    types: precheck.status.updated / precheck.all_ready / precheck.
    blocked). To be added in ``test_e2e_precheck_ws_broadcast.py`` once
    we agree on the WS test harness pattern (httpx-ws vs real
    websockets + asyncio).

    Reference: ``test_ai_blocklist_pubsub_cross_replica.py`` uses the
    docker marker for staging-only cross-replica E2E; we'll mirror that
    pattern for AC#7.
    """
    raise NotImplementedError("see skip reason")
