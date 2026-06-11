"""Schemathesis contract lock for S3-DEV-003-PRECHECK-BACKEND endpoints.

S3-DEV-003 c5 — locks the OpenAPI schema for:

- ``GET /api/v1/users/orders/{order_id}/precheck-status`` (c3 ship)

(The WS endpoint is intentionally excluded; WS upgrade is not part
of the OpenAPI surface — see backend/app/api/v1/ws.py for the
real WS handshake contract.)

## Why a positive list sentinel here?

ABAC Layer 1 schema is the load-bearing enforcement layer (ADR-0048
§7.0). If a new field is added to ``OrderPrecheckSummaryView`` but
forgotten in the negative-list filter, only the sentinel here +
``tests/schemas/test_order_precheck_abac_layer1.py`` catch it before
production. PR-level reviewers cannot eyeball all 4 nested view
classes consistently — the sentinel is the source of truth.

## Why no fuzz generation?

The negative-list sentinel + ABAC schema test + e2e + abac integration
already cover input/auth fuzz exhaustively. schemathesis here adds
**response schema lock**, not input fuzz — same design choice as
``test_prep_package_schemathesis_contract.py`` (魈 architect direction
2026-06-10).

## Positive list sentinels

Field set is the ``OrderPrecheckSummaryView`` top-level fields PLUS
the 4 nested status-view field sets. Drift in any → CI fails.
"""

from __future__ import annotations

import pytest
import schemathesis
from httpx import AsyncClient

from app.core.security import create_access_token
from app.main import app
from app.models.order import OrderStatus
from app.models.user import UserRole

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixture (mirrors test_users_precheck_endpoint.precheck_context but trimmed
# to what schemathesis contract tests need: patient owner + an order).
# ---------------------------------------------------------------------------


@pytest.fixture
async def precheck_context(seed_user, seed_hospital, seed_order):
    """Seed a patient + companion + accepted order for contract-lock tests."""
    patient = await seed_user(phone="13855550101", role=UserRole.patient)
    companion = await seed_user(phone="13855550102", role=UserRole.companion)
    hospital = await seed_hospital(name="Precheck contract test hospital")
    order = await seed_order(
        patient_id=patient.id,
        companion_id=companion.id,
        hospital_id=hospital.id,
        status=OrderStatus.accepted,
    )
    return {
        "patient": patient,
        "companion": companion,
        "order": order,
        "patient_token": create_access_token(
            {"sub": str(patient.id), "role": "patient"}
        ),
    }

# ---------------------------------------------------------------------------
# Positive-list sentinels (S3-DEV-003 c1 schema + c2 evaluate ship lock).
#
# Rule: ANY field rename / add / remove MUST update the matching
# frozenset here + reviewer ack. Prevents silent OpenAPI ↔ Pydantic
# drift (e.g. handler returns 9 fields but schema declares 8).
# ---------------------------------------------------------------------------

SUMMARY_VIEW_TOP_FIELDS: frozenset[str] = frozenset({
    "order_id",
    "contract_status",
    "insurance_status",
    "preparation_status",
    "companion_cert_status",
    "all_ready",
    "payment_enabled",
    "blocked_reason",
    "signed_url_expires_at",
})

# ContractStatusView (5 fields)
CONTRACT_STATUS_FIELDS: frozenset[str] = frozenset({
    "ready",
    "contract_id",
    "contract_template_version",
    "contract_pdf_url",
    "generated_at",
})

# InsuranceStatusView (5 fields — masked / pdf_url / effective date)
INSURANCE_STATUS_FIELDS: frozenset[str] = frozenset({
    "ready",
    "insurance_order_id",
    "insurance_policy_no_masked",
    "insurance_policy_pdf_url",
    "insurance_effective_from",
})

# PreparationStatusView (5 fields)
PREPARATION_STATUS_FIELDS: frozenset[str] = frozenset({
    "ready",
    "preparation_id",
    "prep_summary",
    "sections_count",
    "generated_at",
})

# CompanionCertStatusView (6 fields)
COMPANION_CERT_STATUS_FIELDS: frozenset[str] = frozenset({
    "ready",
    "companion_cert_pseudonym_name",
    "companion_cert_work_id",
    "companion_cert_qualifications",
    "companion_cert_proof_image_urls",
    "companion_cert_verified_at",
})


# ---------------------------------------------------------------------------
# Schema load
# ---------------------------------------------------------------------------


def _load_schema() -> schemathesis.openapi.OpenApiSchema:
    """Load OpenAPI dict from in-process FastAPI app."""
    return schemathesis.openapi.from_dict(app.openapi())


# ---------------------------------------------------------------------------
# Schema lock: 200 response shape
# ---------------------------------------------------------------------------


async def test_precheck_endpoint_200_response_schema_locked(
    client: AsyncClient, precheck_context
):
    """200 response conforms to declared :class:`OrderPrecheckSummaryView` schema."""
    schema = _load_schema()
    op = schema["/api/v1/users/orders/{order_id}/precheck-status"]["GET"]

    order = precheck_context["order"]
    token = precheck_context["patient_token"]

    response = await client.get(
        f"/api/v1/users/orders/{order.id}/precheck-status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200, response.text
    op.validate_response(response)


async def test_precheck_endpoint_404_response_schema_locked(
    client: AsyncClient, precheck_context
):
    """404 hybrid response also conforms to declared OpenAPI ErrorResponse."""
    from uuid import uuid4

    schema = _load_schema()
    op = schema["/api/v1/users/orders/{order_id}/precheck-status"]["GET"]

    token = precheck_context["patient_token"]
    missing_id = uuid4()

    response = await client.get(
        f"/api/v1/users/orders/{missing_id}/precheck-status",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404, response.text
    op.validate_response(response)


# ---------------------------------------------------------------------------
# Field-set sentinel tests
# ---------------------------------------------------------------------------


async def test_summary_view_top_level_field_set_locked(
    client: AsyncClient, precheck_context
):
    """Top-level field set of OrderPrecheckSummaryView must not drift.

    Adding a field to the Pydantic model without updating
    ``SUMMARY_VIEW_TOP_FIELDS`` here fails CI immediately.
    """
    order = precheck_context["order"]
    token = precheck_context["patient_token"]

    response = await client.get(
        f"/api/v1/users/orders/{order.id}/precheck-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert frozenset(body.keys()) == SUMMARY_VIEW_TOP_FIELDS, (
        f"OrderPrecheckSummaryView top-level field set drifted. "
        f"Got: {sorted(body.keys())}, "
        f"expected: {sorted(SUMMARY_VIEW_TOP_FIELDS)}"
    )


async def test_nested_status_view_field_sets_locked(
    client: AsyncClient, precheck_context
):
    """Field sets of the 4 nested status views must not drift."""
    order = precheck_context["order"]
    token = precheck_context["patient_token"]

    response = await client.get(
        f"/api/v1/users/orders/{order.id}/precheck-status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200, response.text
    body = response.json()

    assert frozenset(body["contract_status"].keys()) == CONTRACT_STATUS_FIELDS, (
        f"ContractStatusView field set drifted. "
        f"Got: {sorted(body['contract_status'].keys())}, "
        f"expected: {sorted(CONTRACT_STATUS_FIELDS)}"
    )
    assert frozenset(body["insurance_status"].keys()) == INSURANCE_STATUS_FIELDS, (
        f"InsuranceStatusView field set drifted. "
        f"Got: {sorted(body['insurance_status'].keys())}, "
        f"expected: {sorted(INSURANCE_STATUS_FIELDS)}"
    )
    assert frozenset(body["preparation_status"].keys()) == PREPARATION_STATUS_FIELDS, (
        f"PreparationStatusView field set drifted. "
        f"Got: {sorted(body['preparation_status'].keys())}, "
        f"expected: {sorted(PREPARATION_STATUS_FIELDS)}"
    )
    assert (
        frozenset(body["companion_cert_status"].keys())
        == COMPANION_CERT_STATUS_FIELDS
    ), (
        f"CompanionCertStatusView field set drifted. "
        f"Got: {sorted(body['companion_cert_status'].keys())}, "
        f"expected: {sorted(COMPANION_CERT_STATUS_FIELDS)}"
    )
