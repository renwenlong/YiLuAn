"""Schemathesis 契约 lock for S3-DEV-002-PREP-API endpoints (AC#5).

Locks the response schema of the three prep-package endpoints so any
silent OpenAPI drift (新增字段未声明 / 字段类型偷换 / 反例 schema 漂) fails CI:

- ``GET /api/v1/users/orders/{order_id}/prep-package`` (PR #233 ship, user 全字段)
- ``GET /api/v1/companions/orders/{order_id}/prep-package`` (PR #233 ship, 陪诊师摘要 only)
- ``GET /api/v1/admin/prep-packages/{order_id}`` (PR #233/#238 ship, admin 全字段 + audit log)

## 设计选择 (魈 2026-06-10 architect direction)

- 不用 schemathesis 的 fuzz generation: 我们已有 abac sentinel / e2e / audit-log 整覆盖,
  fuzz 主要价值在反例发现, 而 ABAC 反例已被 sentinel 锁住. 此处 contract lock 关注的是
  **schema 漂移**, 不是 input fuzz.
- 用 ``APIOperation.validate_response()`` 校验真实 httpx 响应符合 OpenAPI schema.
- 字段名集比较 (PR #234 ``test_schema_drift_field_sets_locked_for_all_role_views``)
  已覆盖, 本 PR 不重复 — schemathesis 补位在字段类型 / nullable / enum / UUID format /
  Decimal precision / ErrorResponse 结构这些 jsonschema 级套接.
- 反例 (403 跨 role / 404) 同样验 schema, 防 ErrorResponse / 403 body 偷换格式
  (例如 detail 改 errors 数组 → 前端兼容性炸).

## 不在范围 (与魈对齐)

- AC#4 BudgetGuard 接 generate path: 已拆 ``S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD`` task.
- ABAC fuzz generation: 已被 sentinel + e2e + audit-log 5 个 test 锁, 不重复造车.
- Metric endpoint schema lock: ADR-0048 §7.0.2 metric drift 是另立 task, 不在此 PR.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import schemathesis
from httpx import AsyncClient

from app.main import app

pytest_plugins = ["tests.api.v1.prep_package_abac_fixtures"]
pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Schema load (per-test fresh to allow lifespan dependency wiring in conftest)
# ---------------------------------------------------------------------------


def _load_schema() -> schemathesis.openapi.OpenApiSchema:
    """Pull OpenAPI dict from in-process FastAPI app, hand to schemathesis.

    Using ``from_dict`` (not ``from_asgi``) keeps the schema load purely
    in-process — schemathesis doesn't reach for the network or spin up a
    second TestClient. Validation still walks the same ``app.openapi()``
    spec that ``scripts/dump_openapi.py`` writes to ``docs/api/openapi.json``.
    """
    return schemathesis.openapi.from_dict(app.openapi())


# ---------------------------------------------------------------------------
# Positive list sentinels (ADR-0049 §schemathesis positive list 模式)
#
# 规则: 任何字段名加减必须改这里 + PR + reviewer ack. 防 schema 偷扩 (例如
# 业务模块加字段忘 update OpenAPI 描述, 或反向, OpenAPI 加字段但 handler 没返回).
#
# - USER 视图: 全字段 (ADR-0048 §7.0 用户端)
# - COMPANION 视图: 6 字段摘要 only (ADR-0048 §7.0 陪诊师端隐去成本/原文)
# - ADMIN 视图: 全字段 (ADR-0048 §7.0 admin 端 + audit log; PR #238 不改字段集)
# ---------------------------------------------------------------------------

# UserPrepPackageView (app/schemas/prep_package.py): 8 字段 — 患者全字段, 无 ops metadata.
USER_VIEW_POSITIVE_LIST: frozenset[str] = frozenset({
    "id",
    "order_id",
    "status",
    "user_checked_items",
    "carry_items",
    "pre_visit_notes",
    "possible_questions",
    "companion_focus_points",
})

# CompanionPrepPackageView: 6 字段 — ABAC red line, 隐去 pre_visit_notes / possible_questions /
# raw carry_items / 所有 ops metadata (ADR-0048 §7.0).
COMPANION_VIEW_POSITIVE_LIST: frozenset[str] = frozenset({
    "id",
    "order_id",
    "status",
    "user_checked_items",
    "carry_items_summary",
    "companion_focus_points",
})

# AdminPrepPackageView: 15 字段 — admin 全字段 + ops metadata
# (trace_id / prompt_version_id / model / cost / fallback_reason / generation_time_ms).
ADMIN_VIEW_POSITIVE_LIST: frozenset[str] = frozenset({
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
})


# ---------------------------------------------------------------------------
# Schemathesis schema lock: positive (200) responses
# ---------------------------------------------------------------------------


async def test_user_endpoint_200_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """User endpoint 200 response conforms to declared OpenAPI schema."""
    schema = _load_schema()
    op = schema["/api/v1/users/orders/{order_id}/prep-package"]["GET"]

    order = prep_abac_context["order"]
    token = prep_abac_context["patient_token"]

    response = await client.get(
        f"/api/v1/users/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    op.validate_response(response)


async def test_companion_endpoint_200_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """Companion endpoint 200 response conforms to declared OpenAPI schema."""
    schema = _load_schema()
    op = schema["/api/v1/companions/orders/{order_id}/prep-package"]["GET"]

    order = prep_abac_context["order"]
    token = prep_abac_context["companion_token"]

    response = await client.get(
        f"/api/v1/companions/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    op.validate_response(response)


async def test_admin_endpoint_200_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """Admin endpoint 200 response conforms to declared OpenAPI schema."""
    schema = _load_schema()
    op = schema["/api/v1/admin/prep-packages/{order_id}"]["GET"]

    order = prep_abac_context["order"]
    token = prep_abac_context["admin_token"]

    response = await client.get(
        f"/api/v1/admin/prep-packages/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    op.validate_response(response)


# ---------------------------------------------------------------------------
# Positive list sentinels (字段名漂移 → CI 失败)
#
# Note (2026-06-10): PR #234 在 ``tests/integration/test_prep_package_abac_e2e.py::
# test_schema_drift_field_sets_locked_for_all_role_views`` 已加同型字段集哨兵
# (EXPECTED_USER_FIELDS / EXPECTED_COMPANION_FIELDS / EXPECTED_ADMIN_FIELDS).
# 本文件不重复 — schemathesis 部分专注 schema 结构验证 (字段类型 /
# nullable / enum / UUID format / Decimal precision / ErrorResponse 结构),
# 字面 set 比较走 PR #234 已有哨兵.
#
# 上面 USER_VIEW_POSITIVE_LIST 等 frozenset 仅作为文档参考 (跳转读者看人脑 schema
# 期望), 不再起 assert role.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Negative cases: 跨 role 403 + 404 ErrorResponse schema lock
# ---------------------------------------------------------------------------


async def test_user_endpoint_403_cross_role_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """Companion token on user endpoint -> 403, 错误响应符合 schema."""
    schema = _load_schema()
    op = schema["/api/v1/users/orders/{order_id}/prep-package"]["GET"]

    order = prep_abac_context["order"]
    token = prep_abac_context["companion_token"]

    response = await client.get(
        f"/api/v1/users/orders/{order.id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403, response.text
    op.validate_response(response)


async def test_admin_endpoint_403_cross_role_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """Patient token on admin endpoint -> 403, 错误响应符合 schema."""
    schema = _load_schema()
    op = schema["/api/v1/admin/prep-packages/{order_id}"]["GET"]

    order = prep_abac_context["order"]
    token = prep_abac_context["patient_token"]

    response = await client.get(
        f"/api/v1/admin/prep-packages/{order.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403, response.text
    op.validate_response(response)


async def test_user_endpoint_404_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """User endpoint 404 (订单不存在) -> 错误响应符合 schema."""
    schema = _load_schema()
    op = schema["/api/v1/users/orders/{order_id}/prep-package"]["GET"]

    token = prep_abac_context["patient_token"]
    nonexistent_id = uuid4()

    response = await client.get(
        f"/api/v1/users/orders/{nonexistent_id}/prep-package",
        headers={"Authorization": f"Bearer {token}"},
    )

    # 跨 role / 跨主体 / 不存在 都可能返 403 (订单 ABAC 早于 NotFound 判断) 或 404.
    # 关键: 无论哪种, 错误响应 schema 必须 valid.
    assert response.status_code in (403, 404), response.text
    op.validate_response(response)


async def test_admin_endpoint_404_schema_locked(
    client: AsyncClient, prep_abac_context
):
    """Admin endpoint 404 (订单不存在) -> 错误响应符合 schema."""
    schema = _load_schema()
    op = schema["/api/v1/admin/prep-packages/{order_id}"]["GET"]

    token = prep_abac_context["admin_token"]
    nonexistent_id = uuid4()

    response = await client.get(
        f"/api/v1/admin/prep-packages/{nonexistent_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    # admin 端 ABAC 通过后才查 DB, 不存在 → 404 (NotFoundException → ExceptionHandler).
    assert response.status_code == 404, response.text
    op.validate_response(response)
