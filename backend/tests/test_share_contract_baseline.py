"""[S2-DEV-004] Guard the ADR-0036 §2.7 cross-platform field contract.

These tests fail the moment the live OpenAPI schema drifts from the
committed ``docs/api/share-contract-baseline.json`` — the same check the
``openapi-diff.yml`` CI job runs, but available locally + in the pytest
release gate so drift is caught before push.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.main import app
from scripts.extract_share_contract import (
    CONTRACT_FIELDS,
    DEFAULT_BASELINE,
    _diff,
    extract_contract,
)


def test_baseline_file_exists_and_parses():
    assert DEFAULT_BASELINE.exists(), (
        "share-contract-baseline.json missing — run "
        "`python scripts/extract_share_contract.py --write`"
    )
    data = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    assert "fields" in data and data["fields"]


def test_live_contract_matches_committed_baseline():
    """The headline gate: live schema == committed baseline."""
    baseline = json.loads(DEFAULT_BASELINE.read_text(encoding="utf-8"))
    live = extract_contract(app.openapi())
    diffs = _diff(baseline["fields"], live["fields"])
    assert not diffs, "ADR-0036 §2.7 contract drift:\n" + "\n".join(diffs)


def test_all_seven_canonical_fields_present():
    """Every §2.7 canonical field must appear in at least one schema."""
    live = extract_contract(app.openapi())
    seen = {key.split(".", 1)[1] for key in live["fields"]}
    canonical = {
        "share_token",
        "share_url",
        "share_scope",
        "share_expires_at",
        "share_revoked_at",
        "share_session",
        "share_active_count",
    }
    missing = canonical - seen
    assert not missing, f"§2.7 canonical fields absent from schema: {missing}"


def test_diff_detects_type_change():
    base = {"X.share_token": {"type": "string", "required": True, "enum": None, "nullable": False, "format": None}}
    live = {"X.share_token": {"type": "integer", "required": True, "enum": None, "nullable": False, "format": None}}
    diffs = _diff(base, live)
    assert any("CHANGED" in d and "type" in d for d in diffs)


def test_diff_detects_required_flip():
    base = {"X.share_token": {"type": "string", "required": True, "enum": None, "nullable": False, "format": None}}
    live = {"X.share_token": {"type": "string", "required": False, "enum": None, "nullable": False, "format": None}}
    diffs = _diff(base, live)
    assert any("required" in d for d in diffs)


def test_diff_detects_removed_field():
    base = {"X.share_token": {"type": "string", "required": True, "enum": None, "nullable": False, "format": None}}
    diffs = _diff(base, {})
    assert any("REMOVED" in d for d in diffs)
