"""E2E ABAC matrix for S3 prep package endpoints.

S3-TEST-002-ABAC-E2E:
- 3 endpoints × 3 roles matrix (patient / companion / admin)
- companion red-line field set lock
- payload-size reduction sentinel for companion projection
- schema drift snapshot for all three role views
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from httpx import AsyncClient

pytest_plugins = ["tests.api.v1.prep_package_abac_fixtures"]
pytestmark = pytest.mark.asyncio

USER_ENDPOINT = "user"
COMPANION_ENDPOINT = "companion"
ADMIN_ENDPOINT = "admin"

PATIENT_ROLE = "patient"
COMPANION_ROLE = "companion"
ADMIN_ROLE = "admin"

EXPECTED_USER_FIELDS = {
    "id",
    "order_id",
    "status",
    "user_checked_items",
    "carry_items",
    "pre_visit_notes",
    "possible_questions",
    "companion_focus_points",
}
EXPECTED_COMPANION_FIELDS = {
    "id",
    "order_id",
    "status",
    "user_checked_items",
    "carry_items_summary",
    "companion_focus_points",
}
EXPECTED_ADMIN_FIELDS = {
    "id",
    "order_id",
    "status",
    "user_checked_items",
    "carry_items",
    "pre_visit_notes",
    "possible_questions",
    "companion_focus_points",
    "trace_id",
    "prompt_version_id",
    "model",
    "estimated_cost_yuan",
    "actual_cost_yuan",
    "generation_time_ms",
    "fallback_reason",
}
FORBIDDEN_COMPANION_FIELDS = {
    "pre_visit_notes",
    "possible_questions",
    "carry_items",
    "trace_id",
    "prompt_version_id",
    "model",
    "estimated_cost_yuan",
    "actual_cost_yuan",
    "generation_time_ms",
    "fallback_reason",
}


def _url(endpoint: str, order_id: str) -> str:
    if endpoint == USER_ENDPOINT:
        return f"/api/v1/users/orders/{order_id}/prep-package"
    if endpoint == COMPANION_ENDPOINT:
        return f"/api/v1/companions/orders/{order_id}/prep-package"
    if endpoint == ADMIN_ENDPOINT:
        return f"/api/v1/admin/prep-packages/{order_id}"
    raise AssertionError(f"unknown endpoint: {endpoint}")


def _token(context: Mapping[str, Any], role: str) -> str:
    return {
        PATIENT_ROLE: context["patient_token"],
        COMPANION_ROLE: context["companion_token"],
        ADMIN_ROLE: context["admin_token"],
    }[role]


@pytest.mark.parametrize(
    ("endpoint", "role", "expected_status"),
    [
        (USER_ENDPOINT, PATIENT_ROLE, 200),
        (USER_ENDPOINT, COMPANION_ROLE, 403),
        (USER_ENDPOINT, ADMIN_ROLE, 403),
        (COMPANION_ENDPOINT, PATIENT_ROLE, 403),
        (COMPANION_ENDPOINT, COMPANION_ROLE, 200),
        (COMPANION_ENDPOINT, ADMIN_ROLE, 403),
        (ADMIN_ENDPOINT, PATIENT_ROLE, 403),
        (ADMIN_ENDPOINT, COMPANION_ROLE, 403),
        (ADMIN_ENDPOINT, ADMIN_ROLE, 200),
    ],
)
async def test_abac_3x3_role_endpoint_matrix(
    client: AsyncClient,
    prep_abac_context: Mapping[str, Any],
    endpoint: str,
    role: str,
    expected_status: int,
):
    """AC#1: 9 combinations; only same-role surface gets 200.

    Cross-role responses must be 403 per task description. If admin JWTs
    produce 401 on user/companion surfaces, this test intentionally catches
    the mismatch because it is a product-level ABAC contract drift.
    """

    order = prep_abac_context["order"]
    resp = await client.get(
        _url(endpoint, str(order.id)),
        headers={"Authorization": f"Bearer {_token(prep_abac_context, role)}"},
    )

    assert resp.status_code == expected_status, (
        f"{role} token -> {endpoint} endpoint expected {expected_status}, "
        f"got {resp.status_code}: {resp.text}"
    )


async def test_companion_view_field_set_closed_and_red_line_data_absent(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
):
    """AC#2: companion E2E view has a closed, safe field set."""

    order = prep_abac_context["order"]
    resp = await client.get(
        _url(COMPANION_ENDPOINT, str(order.id)),
        headers={"Authorization": f"Bearer {prep_abac_context['companion_token']}"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    actual_fields = set(body)
    assert actual_fields == EXPECTED_COMPANION_FIELDS, (
        f"陪诊师视图字段集漂移: extra={actual_fields - EXPECTED_COMPANION_FIELDS}, "
        f"missing={EXPECTED_COMPANION_FIELDS - actual_fields}"
    )
    assert not (FORBIDDEN_COMPANION_FIELDS & actual_fields)

    serialized = json.dumps(body, ensure_ascii=False)
    assert "糖尿病" not in serialized
    assert "胰岛素" not in serialized
    assert "是否需要调整用药" not in serialized
    assert "复查周期" not in serialized
    assert "trace-prep-001" not in serialized


async def test_patient_and_admin_views_keep_full_sensitive_content(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
):
    """Positive control: patient/admin see full fields, proving data exists."""

    order = prep_abac_context["order"]
    patient_resp = await client.get(
        _url(USER_ENDPOINT, str(order.id)),
        headers={"Authorization": f"Bearer {prep_abac_context['patient_token']}"},
    )
    admin_resp = await client.get(
        _url(ADMIN_ENDPOINT, str(order.id)),
        headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
    )

    assert patient_resp.status_code == 200, patient_resp.text
    assert admin_resp.status_code == 200, admin_resp.text

    patient = patient_resp.json()
    admin = admin_resp.json()

    assert set(patient) == EXPECTED_USER_FIELDS
    assert patient["pre_visit_notes"] == "患者有糖尿病史，空腹检查需提前沟通。"
    assert patient["possible_questions"] == ["是否需要调整用药？", "复查周期多久？"]
    assert patient["carry_items"] == ["身份证", "医保卡", "既往检查报告"]
    assert "trace_id" not in patient

    assert set(admin) == EXPECTED_ADMIN_FIELDS
    assert admin["pre_visit_notes"] == patient["pre_visit_notes"]
    assert admin["possible_questions"] == patient["possible_questions"]
    assert admin["trace_id"] == "trace-prep-001"
    assert admin["fallback_reason"] == "budget_guard_soft_cap"


async def test_companion_payload_size_reduced_by_more_than_30_percent(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
):
    """AC#3: companion projection payload is materially smaller than full view."""

    order = prep_abac_context["order"]
    admin_resp = await client.get(
        _url(ADMIN_ENDPOINT, str(order.id)),
        headers={"Authorization": f"Bearer {prep_abac_context['admin_token']}"},
    )
    companion_resp = await client.get(
        _url(COMPANION_ENDPOINT, str(order.id)),
        headers={"Authorization": f"Bearer {prep_abac_context['companion_token']}"},
    )

    assert admin_resp.status_code == 200, admin_resp.text
    assert companion_resp.status_code == 200, companion_resp.text

    full_payload_size = len(json.dumps(admin_resp.json(), ensure_ascii=False))
    companion_payload_size = len(json.dumps(companion_resp.json(), ensure_ascii=False))
    reduction = 1 - (companion_payload_size / full_payload_size)

    assert reduction > 0.30, (
        f"companion payload reduction must be >30%; "
        f"got {reduction:.2%} (full={full_payload_size}, companion={companion_payload_size})"
    )


async def test_schema_drift_field_sets_locked_for_all_role_views(
    client: AsyncClient, prep_abac_context: Mapping[str, Any]
):
    """AC#4 local sentinel: role view schemas cannot drift silently."""

    order = prep_abac_context["order"]
    cases = [
        (USER_ENDPOINT, prep_abac_context["patient_token"], EXPECTED_USER_FIELDS),
        (
            COMPANION_ENDPOINT,
            prep_abac_context["companion_token"],
            EXPECTED_COMPANION_FIELDS,
        ),
        (ADMIN_ENDPOINT, prep_abac_context["admin_token"], EXPECTED_ADMIN_FIELDS),
    ]

    for endpoint, token, expected_fields in cases:
        resp = await client.get(
            _url(endpoint, str(order.id)),
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, f"{endpoint}: {resp.text}"
        actual_fields = set(resp.json())
        assert actual_fields == expected_fields, (
            f"{endpoint} schema drift: extra={actual_fields - expected_fields}, "
            f"missing={expected_fields - actual_fields}"
        )
