"""Integration sentinels for prep package ABAC route separation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytest_plugins = ["tests.api.v1.prep_package_abac_fixtures"]
pytestmark = pytest.mark.asyncio


async def test_companion_cannot_access_user_endpoint(
    client: AsyncClient, prep_abac_context
):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["companion_token"]

    # Act
    resp = await client.get(
        f"/api/v1/users/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 403, resp.text


async def test_user_cannot_access_admin_endpoint(client: AsyncClient, prep_abac_context):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["patient_token"]

    # Act
    resp = await client.get(
        f"/api/v1/admin/prep-packages/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 403, resp.text


async def test_companion_view_response_field_set_locked(
    client: AsyncClient, prep_abac_context
):
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["companion_token"]
    expected_fields = {
        "id",
        "order_id",
        "status",
        "user_checked_items",
        "carry_items_summary",
        "companion_focus_points",
    }

    # Act
    resp = await client.get(
        f"/api/v1/companions/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 200, resp.text
    actual_fields = set(resp.json())
    assert actual_fields == expected_fields, (
        f"陪诊师视图字段集漂移! 新字段={actual_fields - expected_fields}, "
        f"缺字段={expected_fields - actual_fields}"
    )


async def test_admin_token_cannot_access_user_endpoint(
    client: AsyncClient, prep_abac_context
):
    """Admin JWT on /users/ -> 403 (auth OK, role-domain wrong).

    Symmetry sentinel: PR #233 made admin endpoints return 403 for valid
    user tokens (vs 401 for missing/invalid). The user endpoint MUST be
    symmetric: valid admin token = 403, not 401 "Invalid token type".
    """
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["admin_token"]

    # Act
    resp = await client.get(
        f"/api/v1/users/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 403, resp.text


async def test_admin_token_cannot_access_companion_endpoint(
    client: AsyncClient, prep_abac_context
):
    """Admin JWT on /companions/ -> 403 (symmetry with above)."""
    # Arrange
    order = prep_abac_context["order"]
    token = prep_abac_context["admin_token"]

    # Act
    resp = await client.get(
        f"/api/v1/companions/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Assert
    assert resp.status_code == 403, resp.text
