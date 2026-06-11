"""ABAC layer 4 sentinel test for ``/v1/companions`` public endpoints.

S3-OPS-ABAC-COMPANIONS-LIST-PII-FIX.

This test is a **schema-level negative-list assertion**: it verifies that
``CompanionDirectoryView`` and ``CompanionDirectoryDetailView`` model field sets
do **NOT** contain any of the forbidden PII fields, regardless of test data
or endpoint behavior.

Defense-in-depth complement to:
  - layer 1: model (CompanionProfile still has real_name, that's OK)
  - layer 2: service (``_to_public_view`` / ``_to_public_detail_view`` strip)
  - layer 3: schema (``CompanionDirectoryView`` positive list)
  - layer 4: this test (sentinel: future schema additions can't reintroduce PII)

If someone later adds ``real_name: str`` field back to ``CompanionDirectoryView``,
this test will fail and block CI before the leak ships.
"""

from __future__ import annotations

import pytest

from app.schemas.companion import (
    COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST,
    CompanionDirectoryDetailView,
    CompanionDirectoryView,
)


@pytest.mark.parametrize(
    "schema_cls",
    [CompanionDirectoryView, CompanionDirectoryDetailView],
    ids=["list_view", "detail_view"],
)
def test_companions_public_view_pii_negative_list(schema_cls):
    """Sentinel: public companion schemas MUST NOT contain PII fields.

    Negative list (source of truth = ``COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST``):
      - ``real_name`` — use ``pseudonym_name`` (mask_name fallback)
      - ``id_number`` — never exposed publicly
      - ``certification_no`` — admin-only
      - ``certification_image_url`` — admin-only (OSS URL is PII vector)
    """
    fields = set(schema_cls.model_fields.keys())
    leaked = fields & COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST
    assert not leaked, (
        f"ABAC LAYER 3 VIOLATION: {schema_cls.__name__} contains PII fields {leaked}. "
        f"Negative list = {sorted(COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST)}. "
        f"If you need a new field, ensure it's NOT in negative list, OR use admin schema."
    )


def test_companions_public_view_has_pseudonym_name():
    """Sentinel: public view must have ``pseudonym_name`` (positive list lock).

    If someone removes pseudonym_name, the endpoint won't return any name at
    all — visible regression rather than silent leak.
    """
    assert "pseudonym_name" in CompanionDirectoryView.model_fields
    assert "pseudonym_name" in CompanionDirectoryDetailView.model_fields


def test_companions_negative_list_immutable():
    """Sentinel: negative list is frozenset (cannot be mutated at runtime)."""
    assert isinstance(COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST, frozenset)
    # 4 required negative fields locked
    required_negative = {
        "real_name",
        "id_number",
        "certification_no",
        "certification_image_url",
    }
    assert required_negative.issubset(COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST), (
        "Required negative fields missing: "
        f"{required_negative - COMPANION_DIRECTORY_VIEW_NEGATIVE_LIST}"
    )


def test_to_public_view_service_layer_masking():
    """Sentinel: ``_to_public_view`` MUST mask real_name → pseudonym_name."""
    from types import SimpleNamespace

    from app.services.companion_profile import _to_public_view

    fake_profile = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        user_id="22222222-2222-2222-2222-222222222222",
        real_name="张三",  # noqa: S106 — test data not a credential
        service_area="海淀区",
        service_types="full_accompany",
        service_hospitals=None,
        service_city="北京",
        bio="测试",
        avg_rating=4.8,
        total_orders=10,
        verification_status="verified",
    )
    view = _to_public_view(fake_profile)

    # PII MUST NOT appear in output
    assert "real_name" not in view, "service-layer leak: real_name in _to_public_view"
    assert "id_number" not in view, "service-layer leak: id_number in _to_public_view"
    # mask_name 应用 (张三 → 张**)
    assert (
        view["pseudonym_name"] == "张**"
    ), f"_to_public_view must mask real_name. got pseudonym_name={view['pseudonym_name']!r}"


def test_to_public_view_handles_empty_real_name():
    """Sentinel: empty/None real_name → pseudonym_name = '' (no crash)."""
    from types import SimpleNamespace

    from app.services.companion_profile import _to_public_view

    for empty_value in (None, "", "  "):
        fake_profile = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            user_id="22222222-2222-2222-2222-222222222222",
            real_name=empty_value,
            service_area=None,
            service_types=None,
            service_hospitals=None,
            service_city=None,
            bio=None,
            avg_rating=0.0,
            total_orders=0,
            verification_status=None,
        )
        view = _to_public_view(fake_profile)
        assert view["pseudonym_name"] == "", (
            f"empty real_name={empty_value!r} should produce empty pseudonym, "
            f"got {view['pseudonym_name']!r}"
        )
