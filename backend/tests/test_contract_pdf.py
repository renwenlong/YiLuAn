"""Tests for S3-DEV-001-CONTRACT-PDF-RENDER (uuid 33ac1174).

AC coverage:
- AC#1 reportlab dependency present (smoke: import works)
- AC#3 _render_pdf returns valid PDF bytes (magic byte)
- AC#3 PDF includes Chinese rendering (no UnicodeEncodeError on 中文 fields)
- AC#4 template_version v1.0.0 round-trips (mismatch raises)
- AC#5 byte-level idempotent (same snapshot → same bytes; critical for
       contract_hash recompute stability across restarts)
- AC: handles 代他人下单 (family_member_name display)
- AC: handles missing companion_name (e.g. snapshot before accept_order
       set it — should not crash, render fallback string)
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.contract_pdf import (
    _format_amount_cny_as_yuan,
    _format_patient_display,
    _format_scheduled,
    render_contract_pdf,
)

# ---------------------------------------------------------------------------
# Helpers — build a minimal Order-shaped object for the renderer.
# We use SimpleNamespace rather than the SQLAlchemy model because the
# renderer is a pure function that only reads attributes; no DB needed.
# ---------------------------------------------------------------------------


def _make_order(**overrides):
    base = dict(
        order_number="YLA1234567890",
        patient_name="张三",
        companion_name="李医生",
        hospital_name="上海第一人民医院",
        service_name_snapshot="全程陪诊",
        service_price_snapshot=Decimal("299.00"),
        appointment_date="2026-06-15",
        appointment_time="14:30",
        family_member_name=None,
        family_member_relation=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _make_hash_inputs(**overrides):
    base = {
        "order_id": str(uuid.uuid4()),
        "amount_cny": 29900,
        "service_package_id": str(uuid.uuid4()),
        "scheduled_at": "2026-06-15T06:30:00+00:00",
        "patient_pseudonym_hash": "a" * 64,
        "companion_id": str(uuid.uuid4()),
        "template_version": "v1.0.0",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# AC: smoke + magic byte
# ---------------------------------------------------------------------------


def test_render_returns_pdf_with_magic_byte():
    pdf = render_contract_pdf(
        order=_make_order(),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert isinstance(pdf, bytes)
    assert pdf.startswith(b"%PDF-"), "must produce valid PDF magic byte for put_contract"
    assert len(pdf) > 200, "real-rendered PDF should be substantially larger than the 14-byte stub"


# ---------------------------------------------------------------------------
# AC#5: byte-level idempotency (critical for contract_hash recompute)
# ---------------------------------------------------------------------------


def test_render_is_byte_level_idempotent():
    """Same inputs MUST produce identical bytes — otherwise WORM blob
    content drift would break hash-based audit verification."""
    order = _make_order()
    hash_inputs = _make_hash_inputs()
    a = render_contract_pdf(
        order=order,
        hash_inputs=hash_inputs,
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    # Call again with the exact same arguments — bytes must match.
    b = render_contract_pdf(
        order=order,
        hash_inputs=hash_inputs,
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert a == b, (
        "PDF render is not byte-level idempotent — reportlab Canvas(invariant=1) "
        "should suppress timestamps / random file IDs. Investigate before merge."
    )


def test_render_changes_when_field_changes():
    """Sanity: the renderer actually reflects input changes (avoid the
    case where idempotency is achieved by ignoring inputs)."""
    base = render_contract_pdf(
        order=_make_order(patient_name="张三"),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    different = render_contract_pdf(
        order=_make_order(patient_name="李四"),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert base != different


# ---------------------------------------------------------------------------
# AC#4: template_version round-trip
# ---------------------------------------------------------------------------


def test_template_version_mismatch_raises():
    with pytest.raises(ValueError, match="template_version mismatch"):
        render_contract_pdf(
            order=_make_order(),
            hash_inputs=_make_hash_inputs(template_version="v1.0.0"),
            contract_hash="d" * 64,
            template_version="v2.0.0",
        )


# ---------------------------------------------------------------------------
# AC: Chinese rendering (no UnicodeEncodeError) + family_member display
# ---------------------------------------------------------------------------


def test_render_handles_chinese_patient_and_companion_name():
    pdf = render_contract_pdf(
        order=_make_order(patient_name="王小明", companion_name="陈大夫"),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert pdf.startswith(b"%PDF-")


def test_render_handles_family_member_booking():
    """F-05 代他人下单: family_member_name takes precedence as the contract subject."""
    pdf = render_contract_pdf(
        order=_make_order(
            patient_name="王小明",
            family_member_name="王老太太",
            family_member_relation="母亲",
        ),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert pdf.startswith(b"%PDF-")


def test_render_handles_missing_companion_name():
    """Defensive: if a contract is rendered before accept_order set
    companion_name, the renderer must not crash; show a fallback."""
    pdf = render_contract_pdf(
        order=_make_order(companion_name=None),
        hash_inputs=_make_hash_inputs(),
        contract_hash="d" * 64,
        template_version="v1.0.0",
    )
    assert pdf.startswith(b"%PDF-")


# ---------------------------------------------------------------------------
# Pure formatter helpers
# ---------------------------------------------------------------------------


def test_format_amount_cny_as_yuan():
    assert _format_amount_cny_as_yuan(0) == "0.00"
    assert _format_amount_cny_as_yuan(1) == "0.01"
    assert _format_amount_cny_as_yuan(99) == "0.99"
    assert _format_amount_cny_as_yuan(29900) == "299.00"
    assert _format_amount_cny_as_yuan(None) == "0.00"


def test_format_patient_display_solo_booking():
    order = _make_order(
        patient_name="张三", family_member_name=None, family_member_relation=None
    )
    assert _format_patient_display(order) == "张三"


def test_format_patient_display_family_member_with_relation():
    order = _make_order(
        patient_name="王小明",
        family_member_name="王老太太",
        family_member_relation="母亲",
    )
    assert _format_patient_display(order) == "王老太太(母亲,由 王小明 代订)"


def test_format_patient_display_family_member_without_relation():
    order = _make_order(
        patient_name="王小明",
        family_member_name="王老太太",
        family_member_relation=None,
    )
    assert _format_patient_display(order) == "王老太太(由 王小明 代订)"


def test_format_patient_display_blank_patient_name():
    order = _make_order(patient_name=None, family_member_name=None)
    assert _format_patient_display(order) == "(未填写)"


def test_format_scheduled_with_date_and_time():
    order = _make_order(appointment_date="2026-06-15", appointment_time="14:30")
    assert _format_scheduled(order) == "2026-06-15 14:30"


def test_format_scheduled_handles_missing_fields():
    order = _make_order(appointment_date=None, appointment_time=None)
    assert _format_scheduled(order) == "(未设定)"
