"""S3-DEV-003-PRECHECK-BACKEND c1 — schema-layer ABAC sentinel.

This is the **physical schema boundary** test for the 5
``OrderPrecheckSummaryView`` family classes. ADR-0048 §7.0 Layer 1:
the views must NOT declare any of the 17 negative-list fields as
properties — that way, no matter what the service layer hands in,
Pydantic serialization cannot leak them.

Design source: ``docs/design/S3-trust-precheck-ui.md`` §5.3 + 设计 17
字段 negative list appendix (table).

Layer 2 (endpoint ABAC) test lives in S3-DEV-003-PRECHECK-BACKEND c3
(GET endpoint test). Layer 3 (service SELECT 列裁剪 lint) lives in c2
(aggregator implementation). Layer 4 = this file + c4 schemathesis
positive-list CI gate.
"""

from __future__ import annotations

import pytest

from app.schemas.order_precheck import (
    CompanionCertStatusView,
    ContractStatusView,
    InsuranceStatusView,
    OrderPrecheckSummaryView,
    PreparationStatusView,
)

# Per design doc §5.3 table — 15 named negative-list fields + 2
# pattern matches (``companion_real_*`` / ``*_id_card_*``). The 15
# named ones are checked verbatim here; the 2 patterns are enforced by
# the c4 Schemathesis positive-list CI gate (pattern matches need a
# regex pass over the response body, not a static schema check).
NEGATIVE_LIST_NAMED_FIELDS: tuple[str, ...] = (
    # Contract
    "contract_hash",
    "hash_inputs",
    "storage_blob_path",
    "template_key",
    # Insurance
    "carrier_internal_id",
    "actual_premium",
    "underwriter_meta",
    # Preparation
    "prompt_version",
    "model_used",
    "raw_llm_output",
    "cost_yuan",
    # Companion cert
    "companion_real_name",
    "companion_id_card_hash",
    "companion_phone",
    "companion_user_id",
)

ALL_VIEWS = (
    OrderPrecheckSummaryView,
    ContractStatusView,
    InsuranceStatusView,
    PreparationStatusView,
    CompanionCertStatusView,
)


def _all_property_names(schema: dict) -> set[str]:
    """Walk ``properties`` at the top level + every ``$defs`` body.

    Only checks **property keys**, not descriptions / docstrings —
    those are allowed to mention negative-list field names as
    self-documenting "do not add" warnings.
    """
    names: set[str] = set(schema.get("properties", {}).keys())
    for def_body in schema.get("$defs", {}).values():
        names.update(def_body.get("properties", {}).keys())
    return names


@pytest.mark.parametrize("view_cls", ALL_VIEWS, ids=lambda c: c.__name__)
def test_view_schema_excludes_15_named_negative_list_fields(view_cls) -> None:
    """Every view MUST NOT declare any of the 15 named negative-list
    fields as a property (Layer 1 ABAC sentinel).

    Failure mode: adding a sensitive field accidentally (e.g. cargo-cult
    "for debugging") slips it through into the OpenAPI schema and from
    there into client SDKs + front-end devtools. This test is the
    physical boundary that stops that at the Pydantic layer.
    """
    schema = view_cls.model_json_schema()
    property_names = _all_property_names(schema)
    leaked = sorted(set(NEGATIVE_LIST_NAMED_FIELDS) & property_names)
    assert not leaked, (
        f"{view_cls.__name__} leaks ABAC negative-list field(s): "
        f"{leaked}. See design §5.3 table. If a field is genuinely "
        f"safe to expose, add it to ORDER_PRECHECK_RESPONSE_POSITIVE_LIST "
        f"with reviewer ack (c4 CI gate); do NOT just add it to the View."
    )


def test_summary_view_has_exactly_expected_top_fields() -> None:
    """Pin the top-level shape of ``OrderPrecheckSummaryView``.

    Catches accidental property additions/removals before they reach
    review (a positive-list snapshot test, complementing the
    negative-list sentinel above).
    """
    schema = OrderPrecheckSummaryView.model_json_schema()
    expected = {
        "order_id",
        "contract_status",
        "insurance_status",
        "preparation_status",
        "companion_cert_status",
        "all_ready",
        "payment_enabled",
        "blocked_reason",
        "signed_url_expires_at",
    }
    actual = set(schema["properties"].keys())
    assert actual == expected, (
        f"OrderPrecheckSummaryView property set changed. "
        f"Expected {sorted(expected)}, got {sorted(actual)}. "
        f"If intentional, update this test AND ORDER_PRECHECK_RESPONSE_"
        f"POSITIVE_LIST (c4 CI gate) AND get reviewer ack."
    )


def test_sub_views_have_exactly_expected_fields() -> None:
    """Pin the positive-list field sets on each sub-view.

    Each list comes from design doc §3.2 verbatim; changes need
    reviewer ack + design doc update + c4 positive-list bump.
    """
    expected = {
        ContractStatusView: {
            "ready",
            "contract_id",
            "contract_template_version",
            "contract_pdf_url",
            "generated_at",
        },
        InsuranceStatusView: {
            "ready",
            "insurance_order_id",
            "insurance_policy_no_masked",
            "insurance_policy_pdf_url",
            "insurance_effective_from",
        },
        PreparationStatusView: {
            "ready",
            "preparation_id",
            "prep_summary",
            "sections_count",
            "generated_at",
        },
        CompanionCertStatusView: {
            "ready",
            "companion_cert_pseudonym_name",
            "companion_cert_work_id",
            "companion_cert_qualifications",
            "companion_cert_proof_image_urls",
            "companion_cert_verified_at",
        },
    }
    for view_cls, want in expected.items():
        actual = set(view_cls.model_json_schema()["properties"].keys())
        assert actual == want, (
            f"{view_cls.__name__} property set changed. "
            f"Expected {sorted(want)}, got {sorted(actual)}."
        )


def test_companion_cert_fields_use_companion_cert_prefix() -> None:
    """ADR-0046 §3.5 positive-list prefix lint — ``CompanionCertStatusView``
    user-visible fields MUST start with ``companion_cert_`` to avoid
    colliding with operator-side ``companion_*`` field naming.

    ``ready`` is the only exception (it's a common boolean shared
    across all 4 views).
    """
    schema = CompanionCertStatusView.model_json_schema()
    fields = set(schema["properties"].keys()) - {"ready"}
    bad = [f for f in fields if not f.startswith("companion_cert_")]
    assert not bad, (
        f"CompanionCertStatusView field(s) missing 'companion_cert_' "
        f"prefix: {sorted(bad)}. ADR-0046 §3.5 lint."
    )


def test_insurance_fields_use_insurance_prefix() -> None:
    """ADR-0046 §3.5 + design §3.2 r2 amend — ``InsuranceStatusView``
    domain-specific fields MUST start with ``insurance_`` to avoid
    silent collision with the admin-side ``policy_*`` field family.

    ``ready`` is exempt (common boolean).
    """
    schema = InsuranceStatusView.model_json_schema()
    fields = set(schema["properties"].keys()) - {"ready"}
    bad = [f for f in fields if not f.startswith("insurance_")]
    assert not bad, (
        f"InsuranceStatusView field(s) missing 'insurance_' prefix: "
        f"{sorted(bad)}. ADR-0046 §3.5 + design §3.2 r2 amend."
    )
