"""ABAC field-level tests for S3 prep package views (ADR-0048 §7.0.2)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytest_plugins = ["tests.api.v1.prep_package_abac_fixtures"]
pytestmark = pytest.mark.asyncio


async def test_companion_view_must_not_contain_pre_visit_notes(
    client: AsyncClient, prep_abac_context
):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["companion_token"]

    # Act
    resp = await client.get(
        f"/api/v1/companions/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "pre_visit_notes" not in body
    assert "possible_questions" not in body
    assert "trace_id" not in body
    assert "carry_items" not in body
    assert "carry_items_summary" in body


async def test_user_view_includes_full_content(client: AsyncClient, prep_abac_context):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["patient_token"]

    # Act
    resp = await client.get(
        f"/api/v1/users/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pre_visit_notes"] == "患者有糖尿病史，空腹检查需提前沟通。"
    assert body["possible_questions"] == ["是否需要调整用药？", "复查周期多久？"]
    assert "trace_id" not in body


async def test_admin_view_includes_trace(client: AsyncClient, prep_abac_context):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["admin_token"]

    # Act
    resp = await client.get(
        f"/api/v1/admin/prep-packages/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["trace_id"] == "trace-prep-001"
    assert "actual_cost_yuan" in body
    assert body["fallback_reason"] == "budget_guard_soft_cap"
